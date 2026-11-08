"""FastAPI application factory with the PostgreSQL-backed session host."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from retail_app.api.authenticated_host import mount_authenticated_procurement_routes
from retail_app.api.session_routes import create_session_router


def create_app(database: Any, *, title: str = "AI Smart Retail API") -> FastAPI:
    """Create the API host and mount procurement endpoints behind session auth.

    Database configuration and lifecycle remain owned by the deployment entrypoint;
    this factory never runs migrations or connects to a production database at import.
    """
    app = FastAPI(title=title)
    mount_authenticated_procurement_routes(app, database)
    app.include_router(create_session_router(database))
    return app
