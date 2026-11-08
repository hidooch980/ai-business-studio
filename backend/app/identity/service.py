from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.app.identity.models import (
    LoginRateLimit,
    Membership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
    UserSession,
)
from backend.app.identity.permissions import PERMISSION_CATALOG
from backend.app.modules.service import provision_tenant_modules
from backend.app.identity.security import (
    hash_password,
    hash_session_token,
    issue_csrf_token,
    issue_session_token,
    verify_password,
)


class IdentityConflictError(ValueError):
    """Raised when an identity resource conflicts with existing state."""


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
        raise IdentityConflictError("An account with this email already exists")
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
    permission_codes = [code for code, _description in PERMISSION_CATALOG]
    permissions_by_code = {
        permission.code: permission
        for permission in db.scalars(select(Permission).where(Permission.code.in_(permission_codes))).all()
    }
    missing_permissions = [
        Permission(code=code, description=description)
        for code, description in PERMISSION_CATALOG
        if code not in permissions_by_code
    ]
    db.add_all(missing_permissions)
    db.flush()
    permissions = [
        permissions_by_code.get(code) or next(item for item in missing_permissions if item.code == code)
        for code in permission_codes
    ]
    owner_role = Role(tenant_id=tenant.id, name="owner", description="Tenant owner", is_system=True)
    db.add(owner_role)
    db.flush()
    db.add_all([RolePermission(role_id=owner_role.id, permission_id=item.id) for item in permissions])
    db.add(MembershipRole(tenant_id=tenant.id, membership_id=membership.id, role_id=owner_role.id))
    provision_tenant_modules(db, tenant_id=tenant.id, actor_user_id=user.id)
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
    assignment = MembershipRole(tenant_id=membership.tenant_id, membership_id=membership.id, role_id=role.id)
    db.add(assignment)
    db.flush()
    return assignment


def create_csrf_token(db: Session, session: UserSession) -> str:
    raw_token, digest = issue_csrf_token()
    session.csrf_token_hash = digest
    db.flush()
    return raw_token


def login_identifier_hash(email: str, client_ip: str, secret: str) -> str:
    normalized_email = email.strip().casefold()
    material = f"{normalized_email}\0{client_ip}".encode()
    return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()


def login_ip_identifier_hash(client_ip: str, secret: str) -> str:
    """Return a keyed identifier shared by login attempts from the same client IP."""
    material = f"ip\0{client_ip}".encode()
    return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()


def login_account_identifier_hash(email: str, secret: str) -> str:
    """Return a keyed identifier shared by attempts against one account across all IPs."""
    normalized_email = email.strip().casefold()
    material = f"account\0{normalized_email}".encode()
    return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()


def prune_login_rate_limits(db: Session, retention_days: int = 30) -> int:
    if retention_days < 1:
        raise ValueError("retention_days must be positive")
    result = db.execute(
        delete(LoginRateLimit).where(LoginRateLimit.updated_at < datetime.now(UTC) - timedelta(days=retention_days))
    )
    return result.rowcount or 0


def is_login_locked(db: Session, identifier_hash: str) -> bool:
    record = db.scalar(select(LoginRateLimit).where(LoginRateLimit.identifier_hash == identifier_hash))
    if record is None or record.locked_until is None:
        return False
    locked_until = record.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until > datetime.now(UTC)


def record_login_failure(
    db: Session,
    *,
    identifier_hash: str,
    max_attempts: int = 8,
    window_seconds: int = 300,
    lock_seconds: int = 900,
) -> bool:
    if max_attempts < 1 or window_seconds < 1 or lock_seconds < 1:
        raise ValueError("Rate-limit values must be positive")
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=window_seconds)
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        insert_statement = sqlite_insert(LoginRateLimit)
    elif dialect == "postgresql":
        insert_statement = postgresql_insert(LoginRateLimit)
    else:
        raise RuntimeError("Login rate limiting requires SQLite or PostgreSQL")
    statement = insert_statement.values(
        id=uuid4(),
        identifier_hash=identifier_hash,
        window_started_at=now,
        failed_attempts=1,
        locked_until=None,
        updated_at=now,
    )
    window_expired = LoginRateLimit.window_started_at < cutoff
    next_attempts = case(
        (window_expired, 1),
        else_=LoginRateLimit.failed_attempts + 1,
    )
    next_locked_until = case(
        (window_expired, None),
        (LoginRateLimit.failed_attempts + 1 >= max_attempts, now + timedelta(seconds=lock_seconds)),
        else_=LoginRateLimit.locked_until,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[LoginRateLimit.identifier_hash],
        set_={
            "window_started_at": case(
                (window_expired, now),
                else_=LoginRateLimit.window_started_at,
            ),
            "failed_attempts": next_attempts,
            "locked_until": next_locked_until,
            "updated_at": now,
        },
    )
    db.execute(statement)
    db.flush()
    return is_login_locked(db, identifier_hash)


def clear_login_failures(db: Session, identifier_hash: str) -> None:
    db.execute(delete(LoginRateLimit).where(LoginRateLimit.identifier_hash == identifier_hash))
    db.flush()
