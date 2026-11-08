"""Tenant-aware PostgreSQL transaction boundary.

The tenant ID must come from a trusted AccessContext, never directly from request input.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Protocol


class TransactionConnection(Protocol):
    def execute(self, query: str, params: tuple[object, ...] | None = None, **kwargs: object) -> object: ...
    def transaction(self) -> object: ...


class DatabaseConfigurationError(RuntimeError):
    """Raised when database configuration is missing or invalid."""


class PostgresDatabase:
    """Small connection-per-unit-of-work adapter using psycopg 3."""

    def __init__(self, dsn: str) -> None:
        if not dsn or not dsn.strip():
            raise DatabaseConfigurationError("database DSN is required")
        self._dsn = dsn

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise DatabaseConfigurationError(
                "install the PostgreSQL extra with psycopg[binary]"
            ) from exc
        return psycopg.connect(self._dsn)

    @contextmanager
    def transaction(self) -> Iterator[TransactionConnection]:
        """Yield one connection; commit on success and rollback on exception."""
        with self._connect() as connection:
            with connection.transaction():
                yield connection

    @contextmanager
    def tenant_transaction(
        self, *, tenant_id: str, subject_id: str | None = None
    ) -> Iterator[TransactionConnection]:
        """Set transaction-local RLS context before any tenant data access."""
        if not tenant_id or not tenant_id.strip():
            raise ValueError("trusted tenant_id is required")
        with self.transaction() as connection:
            connection.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (tenant_id,),
            )
            if subject_id is not None:
                if not subject_id.strip():
                    raise ValueError("subject_id cannot be blank")
                connection.execute(
                    "SELECT set_config('app.subject_id', %s, true)",
                    (subject_id,),
                )
            yield connection
