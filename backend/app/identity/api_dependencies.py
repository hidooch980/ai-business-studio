import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import get_db_session
from backend.app.identity.models import Membership, Tenant, User, UserSession
from backend.app.identity.security import verify_csrf_token
from backend.app.identity.service import get_active_session


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user: User
    session: UserSession


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
    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
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
