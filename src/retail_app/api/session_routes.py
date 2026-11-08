"""Cookie-based refresh and logout endpoints for server-managed sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from retail_app.security.session_service import (
    RefreshTokenReplayError,
    SessionAuthenticationError,
    SessionService,
)

COOKIE_NAME = "__Host-retail_session"


def _require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if origin != expected or request.headers.get("sec-fetch-site", "same-origin") in {
        "cross-site",
        "same-site",
    }:
        raise HTTPException(status_code=403, detail="same-origin request required")


def create_session_router(database: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
    service = SessionService(database)

    @router.post("/refresh", status_code=204)
    def refresh(request: Request, response: Response) -> Response:
        _require_same_origin(request)
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="authentication required")
        try:
            issued = service.rotate(token)
        except RefreshTokenReplayError as exc:
            response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
            raise HTTPException(status_code=401, detail="session expired; sign in again") from exc
        except SessionAuthenticationError as exc:
            response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
            raise HTTPException(status_code=401, detail="session expired; sign in again") from exc
        response.set_cookie(
            COOKIE_NAME,
            issued.refresh_token,
            max_age=int((issued.expires_at - datetime.now(UTC)).total_seconds()),
            path="/",
            secure=True,
            httponly=True,
            samesite="strict",
        )
        response.status_code = 204
        return response

    @router.post("/logout", status_code=204)
    def logout(request: Request, response: Response) -> Response:
        _require_same_origin(request)
        token = request.cookies.get(COOKIE_NAME)
        if token:
            service.revoke(token)
        response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
        response.status_code = 204
        return response

    return router
