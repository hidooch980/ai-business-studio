from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_permission
from backend.app.identity.models import AuditEvent, Membership, MembershipRole, Role, Tenant, TenantInvitation, User
from backend.app.identity.security import hash_password, hash_session_token, issue_session_token
from backend.app.identity.service import normalize_email

router = APIRouter(prefix="/invitations", tags=["tenant-invitations"])
InviteEmail = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]
InviteName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class InvitationCreateRequest(BaseModel):
    email: InviteEmail
    display_name: InviteName
    role_id: UUID


class InvitationAcceptRequest(BaseModel):
    token: Annotated[str, StringConstraints(min_length=32, max_length=128)]
    password: Annotated[str, StringConstraints(min_length=12, max_length=256)]
    display_name: InviteName | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _active_invitation(invitation: TenantInvitation, now: datetime) -> bool:
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return invitation.accepted_at is None and invitation.revoked_at is None and expires_at > now


def _audit(db: Session, *, tenant_id: UUID, actor_user_id: UUID | None, action: str, invitation_id: UUID) -> None:
    db.add(AuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type="invitation",
        resource_id=str(invitation_id),
        outcome="success",
    ))


@router.get("")
def list_invitations(
    principal: TenantPrincipal = Depends(require_permission("users.read")),
    db: Session = Depends(get_db_session),
) -> dict:
    rows = db.scalars(
        select(TenantInvitation)
        .where(TenantInvitation.tenant_id == principal.tenant.id)
        .order_by(TenantInvitation.created_at.desc(), TenantInvitation.id)
    ).all()
    now = _now()
    return {"items": [{
        "id": str(item.id),
        "email": item.email,
        "display_name": item.display_name,
        "role_id": str(item.role_id) if item.role_id else None,
        "expires_at": item.expires_at.isoformat(),
        "accepted_at": item.accepted_at.isoformat() if item.accepted_at else None,
        "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
        "is_pending": _active_invitation(item, now),
        "created_at": item.created_at.isoformat(),
    } for item in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreateRequest,
    principal: TenantPrincipal = Depends(require_permission("users.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    try:
        email = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A valid email address is required") from exc
    if db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    role = db.scalar(select(Role).where(Role.id == payload.role_id, Role.tenant_id == principal.tenant.id))
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    now = _now()
    recent_count = db.scalar(select(func.count(TenantInvitation.id)).where(
        TenantInvitation.tenant_id == principal.tenant.id,
        TenantInvitation.created_at >= now - timedelta(hours=1),
    )) or 0
    if recent_count >= 20:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Invitation rate limit exceeded")
    pending = db.scalars(select(TenantInvitation).where(
        TenantInvitation.tenant_id == principal.tenant.id,
        func.lower(TenantInvitation.email) == email,
        TenantInvitation.accepted_at.is_(None),
        TenantInvitation.revoked_at.is_(None),
    )).all()
    if any(_active_invitation(item, now) for item in pending):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A pending invitation already exists for this email")
    raw_token, token_hash = issue_session_token()
    invitation = TenantInvitation(
        tenant_id=principal.tenant.id,
        email=email,
        display_name=payload.display_name.strip(),
        role_id=role.id,
        token_hash=token_hash,
        created_by_user_id=principal.user.id,
        expires_at=now + timedelta(hours=72),
    )
    db.add(invitation)
    try:
        db.flush()
        _audit(db, tenant_id=principal.tenant.id, actor_user_id=principal.user.id, action="invitation.created", invitation_id=invitation.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation could not be created") from exc
    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "expires_at": invitation.expires_at.isoformat(),
        "invitation_token": raw_token,
        "delivery": "manual",
        "message": "Token is shown once. Deliver it through a trusted channel; no email provider is configured.",
    }


@router.post("/{invitation_id}/resend")
def resend_invitation(
    invitation_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("users.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    invitation = db.scalar(select(TenantInvitation).where(
        TenantInvitation.id == invitation_id,
        TenantInvitation.tenant_id == principal.tenant.id,
    ).with_for_update())
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation is no longer pending")
    if db.scalar(select(User.id).where(func.lower(User.email) == invitation.email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    raw_token, invitation.token_hash = issue_session_token()
    invitation.expires_at = _now() + timedelta(hours=72)
    _audit(db, tenant_id=principal.tenant.id, actor_user_id=principal.user.id, action="invitation.resent", invitation_id=invitation.id)
    db.commit()
    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "expires_at": invitation.expires_at.isoformat(),
        "invitation_token": raw_token,
        "delivery": "manual",
        "message": "Previous token is invalid. Deliver this new token through a trusted channel.",
    }


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("users.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> None:
    invitation = db.scalar(select(TenantInvitation).where(
        TenantInvitation.id == invitation_id,
        TenantInvitation.tenant_id == principal.tenant.id,
    ).with_for_update())
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Accepted invitations cannot be revoked")
    if invitation.revoked_at is None:
        invitation.revoked_at = _now()
        _audit(db, tenant_id=principal.tenant.id, actor_user_id=principal.user.id, action="invitation.revoked", invitation_id=invitation.id)
        db.commit()


@router.post("/accept", status_code=status.HTTP_201_CREATED)
def accept_invitation(
    payload: InvitationAcceptRequest,
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    token_hash = hash_session_token(payload.token)
    invitation = db.scalar(select(TenantInvitation).where(
        TenantInvitation.token_hash == token_hash,
    ).with_for_update())
    now = _now()
    if invitation is None or not _active_invitation(invitation, now):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is invalid or expired")
    tenant = db.scalar(select(Tenant).where(Tenant.id == invitation.tenant_id, Tenant.is_active.is_(True)))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is invalid or expired")
    if db.scalar(select(User.id).where(func.lower(User.email) == invitation.email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    role = db.scalar(select(Role).where(Role.id == invitation.role_id, Role.tenant_id == tenant.id))
    if role is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation role is no longer available")
    user = User(
        email=invitation.email,
        password_hash=hash_password(payload.password),
        display_name=(payload.display_name or invitation.display_name).strip(),
    )
    db.add(user)
    try:
        db.flush()
        membership = Membership(tenant_id=tenant.id, user_id=user.id)
        db.add(membership)
        db.flush()
        db.add(MembershipRole(tenant_id=tenant.id, membership_id=membership.id, role_id=role.id))
        invitation.accepted_at = now
        _audit(db, tenant_id=tenant.id, actor_user_id=user.id, action="invitation.accepted", invitation_id=invitation.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation could not be accepted") from exc
    return {"user_id": str(user.id), "tenant_id": str(tenant.id), "membership_id": str(membership.id), "email": user.email}
