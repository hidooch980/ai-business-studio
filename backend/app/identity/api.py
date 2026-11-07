from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import (
    AuthenticatedPrincipal,
    build_auth_context,
    get_authenticated_principal,
    require_csrf_protection,
)
from backend.app.identity.api_schemas import AuthContextResponse, LoginRequest, RegisterRequest
from backend.app.identity.models import AuditEvent
from backend.app.identity.service import (
    IdentityConflictError,
    create_csrf_token,
    authenticate_user,
    create_user_session,
    register_user,
    revoke_session,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _set_session_cookie(response: Response, token: str, csrf_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_lifetime_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.session_lifetime_seconds,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/api/v1",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/api/v1/auth",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/api/v1",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )


@router.post("/register", response_model=AuthContextResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db_session),
    _csrf: None = Depends(require_csrf_protection),
) -> dict:
    settings = get_settings()
    if not settings.allow_public_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Public registration is disabled")
    try:
        user, tenant, _membership = register_user(
            db,
            tenant_name=payload.tenant_name,
            tenant_slug=payload.tenant_slug,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
        token, session = create_user_session(
            db,
            user=user,
            lifetime=timedelta(seconds=settings.session_lifetime_seconds),
        )
        csrf_token = create_csrf_token(db, session)
        db.add(
            AuditEvent(
                tenant_id=tenant.id,
                actor_user_id=user.id,
                action="auth.register",
                resource_type="user",
                resource_id=str(user.id),
                outcome="success",
            )
        )
        db.commit()
    except IdentityConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration could not be completed") from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration could not be completed") from exc
    except Exception:
        db.rollback()
        raise
    _set_session_cookie(response, token, csrf_token)
    return build_auth_context(db, user)


@router.post("/login", response_model=AuthContextResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db_session),
    _csrf: None = Depends(require_csrf_protection),
) -> dict:
    user = authenticate_user(db, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    settings = get_settings()
    token, session = create_user_session(
        db,
        user=user,
        lifetime=timedelta(seconds=settings.session_lifetime_seconds),
    )
    csrf_token = create_csrf_token(db, session)
    db.add(
        AuditEvent(
            actor_user_id=user.id,
            action="auth.login",
            resource_type="user",
            resource_id=str(user.id),
            outcome="success",
        )
    )
    db.commit()
    _set_session_cookie(response, token, csrf_token)
    return build_auth_context(db, user)


@router.get("/me", response_model=AuthContextResponse)
def current_session(
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
    db: Session = Depends(get_db_session),
) -> dict:
    return build_auth_context(db, principal.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
    _csrf: None = Depends(require_csrf_protection),
) -> Response:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token and revoke_session(db, token):
        db.commit()
    else:
        db.rollback()
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
