from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
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
from backend.app.identity.models import AuditEvent, UserSession
from backend.app.identity.service import (
    IdentityConflictError,
    authenticate_user,
    clear_login_failures,
    create_csrf_token,
    create_user_session,
    is_login_locked,
    login_identifier_hash,
    record_login_failure,
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
        path="/api/v1",
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
        path="/api/v1",
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
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
    _csrf: None = Depends(require_csrf_protection),
) -> dict:
    settings = get_settings()
    client_ip = request.client.host if request.client is not None else "unknown"
    identifier_hash = login_identifier_hash(payload.email, client_ip, settings.auth_rate_limit_secret)
    if is_login_locked(db, identifier_hash):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts. Try again later.")
    user = authenticate_user(db, email=payload.email, password=payload.password)
    if user is None:
        locked = record_login_failure(
            db,
            identifier_hash=identifier_hash,
            max_attempts=settings.auth_rate_limit_attempts,
            window_seconds=settings.auth_rate_limit_window_seconds,
            lock_seconds=settings.auth_rate_limit_lock_seconds,
        )
        db.add(
            AuditEvent(
                action="auth.login_failed",
                resource_type="identity",
                resource_id=identifier_hash,
                outcome="denied",
            )
        )
        db.commit()
        if locked:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts. Try again later.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    clear_login_failures(db, identifier_hash)
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


@router.get("/sessions")
def list_user_sessions(
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
    db: Session = Depends(get_db_session),
) -> dict:
    sessions = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == principal.user.id)
        .order_by(UserSession.created_at.desc(), UserSession.id.desc())
        .limit(50)
    ).all()
    now = datetime.now(UTC)
    return {
        "items": [
            {
                "id": str(item.id),
                "created_at": item.created_at.isoformat(),
                "expires_at": item.expires_at.isoformat(),
                "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
                "is_current": item.id == principal.session.id,
                "is_active": item.revoked_at is None
                and (item.expires_at.replace(tzinfo=UTC) if item.expires_at.tzinfo is None else item.expires_at) > now,
            }
            for item in sessions
        ]
    }


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_session(
    session_id: str,
    response: Response,
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> Response:
    try:
        target_id = UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found") from exc
    target = db.scalar(
        select(UserSession)
        .where(UserSession.id == target_id, UserSession.user_id == principal.user.id)
        .with_for_update()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if target.revoked_at is None:
        target.revoked_at = datetime.now(UTC)
        db.add(
            AuditEvent(
                actor_user_id=principal.user.id,
                action="auth.session_revoked",
                resource_type="user_session",
                resource_id=str(target.id),
                outcome="success",
            )
        )
        db.commit()
    if target.id == principal.session.id:
        _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response



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
