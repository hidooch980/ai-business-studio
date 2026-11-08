"""OTP login, session rotation and logout HTTP routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from retail_app.api.auth_context import require_authenticated_access_context
from retail_app.security.auth_service import AuthService
from retail_app.security.authorization import AccessContext

SESSION_COOKIE = "__Host-retail_session"
CSRF_COOKIE = "__Host-retail_csrf"


class OTPRequest(BaseModel):
    identifier: str = Field(min_length=5, max_length=254)


class OTPVerify(BaseModel):
    identifier: str = Field(min_length=5, max_length=254)
    challenge_id: UUID
    code: str = Field(pattern=r"^[0-9]{6}$")
    tenant_id: UUID


def _set_session_cookies(response: Response, raw_token: str, csrf_token: str, ttl: int) -> None:
    response.set_cookie(
        SESSION_COOKIE, raw_token, max_age=ttl, path="/", secure=True,
        httponly=True, samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=ttl, path="/", secure=True,
        httponly=False, samesite="strict",
    )


def _require_same_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    if not origin:
        raise HTTPException(status_code=403, detail="Origin header required")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if origin.rstrip("/") != expected.rstrip("/"):
        raise HTTPException(status_code=403, detail="cross-origin authentication request denied")


def create_auth_router(service: AuthService, *, session_ttl_seconds: int = 2592000) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["authentication"])

    @router.post("/otp/request", status_code=202)
    def request_otp(body: OTPRequest, request: Request) -> dict[str, str]:
        _require_same_origin(request)
        service.request_otp(body.identifier)
        return {"status": "accepted", "message": "If the account exists, a code has been sent."}

    @router.post("/otp/verify")
    def verify_otp(body: OTPVerify, request: Request, response: Response) -> dict[str, str]:
        _require_same_origin(request)
        raw_token, csrf_token = service.verify_otp(
            challenge_id=body.challenge_id,
            identifier=body.identifier,
            code=body.code,
            tenant_id=str(body.tenant_id),
        )
        _set_session_cookies(response, raw_token, csrf_token, session_ttl_seconds)
        return {"status": "authenticated"}

    @router.post("/session/rotate")
    def rotate_session(
        request: Request,
        response: Response,
        context: AccessContext = Depends(require_authenticated_access_context),  # noqa: B008
    ) -> dict[str, str]:
        session_id = getattr(request.state, "session_id", None)
        if not session_id:
            raise HTTPException(status_code=401, detail="authentication required")
        raw_token, csrf_token = service.rotate_session(context, str(session_id))
        _set_session_cookies(response, raw_token, csrf_token, session_ttl_seconds)
        return {"status": "rotated"}

    @router.post("/logout")
    def logout(
        request: Request,
        response: Response,
        context: AccessContext = Depends(require_authenticated_access_context),
    ) -> dict[str, str]:
        session_id = getattr(request.state, "session_id", None)
        if session_id:
            service.revoke_session(context, str(session_id))
        response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        response.delete_cookie(CSRF_COOKIE, path="/", secure=True, httponly=False, samesite="strict")
        return {"status": "logged_out"}

    return router
