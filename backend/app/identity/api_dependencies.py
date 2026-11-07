from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import get_db_session
from backend.app.identity.models import Membership, Tenant, User, UserSession
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
