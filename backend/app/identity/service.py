from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.identity.models import Membership, MembershipRole, Tenant, User, UserSession
from backend.app.identity.security import hash_password, hash_session_token, issue_session_token, verify_password


def normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("A valid email address is required")
    return normalized


def register_user(
    db: Session,
    *,
    tenant_name: str,
    tenant_slug: str,
    email: str,
    password: str,
    display_name: str,
) -> tuple[User, Tenant, Membership]:
    normalized_email = normalize_email(email)
    if db.scalar(select(User.id).where(User.email == normalized_email)) is not None:
        raise ValueError("An account with this email already exists")
    tenant = Tenant(name=tenant_name.strip(), slug=tenant_slug.strip().casefold())
    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
    )
    db.add_all([tenant, user])
    db.flush()
    membership = Membership(tenant_id=tenant.id, user_id=user.id)
    db.add(membership)
    db.flush()
    return user, tenant, membership


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    try:
        normalized_email = normalize_email(email)
    except ValueError:
        return None
    user = db.scalar(select(User).where(User.email == normalized_email, User.is_active.is_(True)))
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def create_user_session(
    db: Session,
    *,
    user: User,
    lifetime: timedelta = timedelta(hours=12),
) -> tuple[str, UserSession]:
    if lifetime <= timedelta(0) or lifetime > timedelta(days=30):
        raise ValueError("Session lifetime must be between 0 and 30 days")
    raw_token, digest = issue_session_token()
    record = UserSession(
        user_id=user.id,
        token_hash=digest,
        expires_at=datetime.now(UTC) + lifetime,
    )
    db.add(record)
    db.flush()
    return raw_token, record


def get_active_session(db: Session, token: str) -> UserSession | None:
    digest = hash_session_token(token)
    record = db.scalar(select(UserSession).where(UserSession.token_hash == digest))
    if record is None or record.revoked_at is not None:
        return None
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    return record


def revoke_session(db: Session, token: str) -> bool:
    record = get_active_session(db, token)
    if record is None:
        return False
    record.revoked_at = datetime.now(UTC)
    db.flush()
    return True


def assign_role_to_membership(
    db: Session,
    *,
    membership: Membership,
    role_id: UUID,
) -> MembershipRole:
    from backend.app.identity.models import Role

    role = db.get(Role, role_id)
    if role is None or role.tenant_id != membership.tenant_id:
        raise ValueError("Role and membership must belong to the same tenant")
    assignment = MembershipRole(membership_id=membership.id, role_id=role.id)
    db.add(assignment)
    db.flush()
    return assignment
