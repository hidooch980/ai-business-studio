"""Fail-closed FastAPI mounting for authenticated procurement routes."""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from retail_app.api.procurement import create_procurement_router
from retail_app.security.authorization import AccessContext


AccessContextResolver = Callable[[Request], AccessContext | Awaitable[AccessContext]]


async def require_authenticated_access_context(request: Request) -> AccessContext:
    """Resolve an active context using only the host's trusted session resolver."""
    resolver = getattr(request.app.state, "access_context_resolver", None)
    if not callable(resolver):
        raise HTTPException(status_code=503, detail="authenticated session resolver is not configured")

    if inspect.iscoroutinefunction(resolver):
        resolved = await cast(Awaitable[AccessContext], resolver(request))
    else:
        resolved = await run_in_threadpool(resolver, request)
        if inspect.isawaitable(resolved):
            resolved = await cast(Awaitable[AccessContext], resolved)

    if not isinstance(resolved, AccessContext) or not resolved.active:
        raise HTTPException(status_code=401, detail="authentication required")
    if not resolved.subject_id or not resolved.tenant_id:
        raise HTTPException(status_code=401, detail="incomplete authenticated identity")
    return resolved


def mount_procurement_routes(
    app: FastAPI,
    database: object,
    *,
    access_context_resolver: AccessContextResolver,
) -> None:
    """Mount procurement routes with an explicitly supplied trusted resolver."""
    if not callable(access_context_resolver):
        raise TypeError("a trusted access_context_resolver is required")
    if any(getattr(route, "path", "").startswith("/api/procurement") for route in app.routes):
        raise RuntimeError("procurement routes are already mounted")

    app.state.access_context_resolver = access_context_resolver
    app.include_router(
        create_procurement_router(database, require_authenticated_access_context)
    )
