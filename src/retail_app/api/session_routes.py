"""Cookie-based refresh and logout endpoints for server-managed sessions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from retail_app.security.authorization import AccessContext
from retail_app.security.session_service import (
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


def create_session_router(
    database: Any,
    *,
    context_dependency: Callable[..., AccessContext],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
    service = SessionService(database)

    @router.get("/sessions")
    def list_sessions(
        context: Annotated[AccessContext, Depends(context_dependency)],
    ) -> list[dict[str, object]]:
        if context.session_id is None or context.session_token_hash is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return service.list_sessions(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            current_session_id=context.session_id,
            session_token_hash=context.session_token_hash,
            expected_role=context.role.value,
            expected_branch_ids=context.branch_ids,
        )

    @router.delete("/sessions/{session_id}", status_code=204)
    def revoke_selected_session(
        session_id: UUID,
        request: Request,
        response: Response,
        context: Annotated[AccessContext, Depends(context_dependency)],
    ) -> Response:
        _require_same_origin(request)
        if context.session_id is None or context.session_token_hash is None:
            raise HTTPException(status_code=401, detail="authentication required")
        revoked = service.revoke_session(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            current_session_id=context.session_id,
            session_token_hash=context.session_token_hash,
            expected_role=context.role.value,
            expected_branch_ids=context.branch_ids,
            target_session_id=str(session_id),
        )
        if not revoked:
            raise HTTPException(status_code=404, detail="session not found")
        if str(session_id) == context.session_id:
            response.delete_cookie(
                COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict"
            )
        response.status_code = 204
        return response

    @router.post("/refresh", status_code=204)
    def refresh(request: Request, response: Response) -> Response:
        _require_same_origin(request)
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="authentication required")
        try:
            issued = service.rotate(token)
        except SessionAuthenticationError:
            response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
            response.status_code = 401
            return response
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
