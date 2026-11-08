"""Executable FastAPI entry point.

Configure DATABASE_URL with the restricted Runtime DSN before starting Uvicorn.
"""
# ruff: noqa: I001
import os

from retail_app.api.host import create_app
from retail_app.infrastructure.database import PostgresDatabase


_database_url = os.environ.get("DATABASE_URL")
if not _database_url:
    raise RuntimeError("DATABASE_URL must be configured before starting the API host")

app = create_app(PostgresDatabase(_database_url))
