"""Explicit FastAPI host mounting for DB-backed procurement authentication."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from retail_app.api.procurement import create_procurement_router
from retail_app.api.session_resolver import PostgresSessionResolver


def mount_authenticated_procurement_routes(
    app: FastAPI,
    database: Any,
    *,
    session_resolver: PostgresSessionResolver | None = None,
) -> PostgresSessionResolver:
    """Mount procurement routes with the DB-backed cookie resolver.

    The resolver is created once per host and used as the dependency for every
    procurement route. No request-supplied tenant, role or branch claims are used.
    """
    existing = getattr(app.state, "session_resolver", None)
    if existing is not None:
        if session_resolver is not None and existing is not session_resolver:
            raise RuntimeError("a different session resolver is already mounted")
        return existing

    resolver = session_resolver or PostgresSessionResolver(database)
    app.state.session_resolver = resolver
    app.include_router(create_procurement_router(database, context_dependency=resolver))
    return resolver
