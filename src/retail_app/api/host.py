"""FastAPI host wiring PostgreSQL session authentication to business APIs."""
from __future__ import annotations

from fastapi import FastAPI

from retail_app.api.auth import create_auth_router
from retail_app.api.auth_context import mount_procurement_routes
from retail_app.infrastructure.database import PostgresDatabase
from retail_app.security.auth_service import AuthService
from retail_app.security.session_resolver import SessionResolver


def create_app(
    database: PostgresDatabase,
    *,
    session_cookie_name: str = "__Host-retail_session",
    auth_service: AuthService | None = None,
) -> FastAPI:
    """Create the API host; OTP routes exist only with an injected delivery service."""
    app = FastAPI(title="AI Business Studio API", version="0.2.0")
    resolver = SessionResolver(database, cookie_name=session_cookie_name)
    mount_procurement_routes(
        app,
        database,
        access_context_resolver=resolver,
    )
    if auth_service is not None:
        app.include_router(create_auth_router(auth_service))

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
