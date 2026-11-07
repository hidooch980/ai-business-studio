import hmac
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import get_db_session
from backend.app.identity.authorization import membership_has_permission
from backend.app.identity.models import Membership, Tenant, User, UserSession
from backend.app.identity.security import verify_csrf_token
from backend.app.identity.service import get_active_session


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user: User
    session: UserSession


@dataclass(frozen=True)
class TenantPrincipal:
    user: User
    session: UserSession
    membership: Membership
    tenant: Tenant


def get_authenticated_principal(
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthenticatedPrincipal:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    session = get_active_session(db, token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = db.scalar(select(User).where(User.id == session.user_id, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return AuthenticatedPrincipal(user=user, session=session)


def get_tenant_principal(
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
    tenant_id: str = Header(alias="X-Tenant-ID"),
    db: Session = Depends(get_db_session),
) -> TenantPrincipal:
    try:
        requested_tenant_id = UUID(tenant_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid X-Tenant-ID is required") from exc
    row = db.execute(
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(
            Membership.user_id == principal.user.id,
            Membership.tenant_id == requested_tenant_id,
            Membership.is_active.is_(True),
            Tenant.is_active.is_(True),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    membership, tenant = row
    return TenantPrincipal(
        user=principal.user,
        session=principal.session,
        membership=membership,
        tenant=tenant,
    )


def require_permission(permission_code: str):
    if not permission_code or permission_code.strip() != permission_code:
        raise ValueError("permission_code must be a non-empty normalized string")

    def dependency(
        tenant_principal: TenantPrincipal = Depends(get_tenant_principal),
        db: Session = Depends(get_db_session),
    ) -> TenantPrincipal:
        if not membership_has_permission(db, tenant_principal.membership, permission_code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return tenant_principal

    return dependency


def build_auth_context(db: Session, user: User) -> dict:
    rows = db.execute(
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
            Tenant.is_active.is_(True),
        )
        .order_by(Tenant.name, Tenant.id)
    ).all()
    return {
        "user": user,
        "memberships": [
            {
                "id": membership.id,
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "tenant_slug": tenant.slug,
            }
            for membership, tenant in rows
        ],
    }


def require_csrf_protection(
    request: Request,
    db: Session = Depends(get_db_session),
) -> None:
    settings = get_settings()
    source_origin = request.headers.get("origin") or request.headers.get("referer")
    if source_origin:
        try:
            parsed_origin = urlsplit(source_origin)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Untrusted request origin") from exc
        request_host = request.headers.get("host", "").casefold()
        if (
            parsed_origin.scheme not in {"http", "https"}
            or not parsed_origin.netloc
            or parsed_origin.netloc.casefold() != request_host
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Untrusted request origin")
    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        if not source_origin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is required")
        return
    session = get_active_session(db, session_token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    if session.csrf_token_hash is None and request.url.path.endswith("/logout"):
        return
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get("X-CSRF-Token")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
        or not verify_csrf_token(header_token, session.csrf_token_hash)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
