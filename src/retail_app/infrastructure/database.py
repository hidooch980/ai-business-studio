"""Tenant-aware PostgreSQL transaction boundary.

The tenant and subject IDs must come from a trusted, database-backed AccessContext.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol


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
        with self._connect() as connection, connection.transaction():
            yield connection

    @contextmanager
    def tenant_transaction(
        self,
        *,
        tenant_id: str,
        subject_id: str | None = None,
        expected_role: str | None = None,
        expected_branch_ids: frozenset[str] | None = None,
    ) -> Iterator[TransactionConnection]:
        """Set transaction-local RLS context and revalidate current access state."""
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
                identity = connection.execute(
                    "SELECT is_active FROM identities WHERE id = %s",
                    (subject_id,),
                ).fetchone()
                tenant = connection.execute(
                    "SELECT status FROM tenants WHERE id = %s",
                    (tenant_id,),
                ).fetchone()
                membership = connection.execute(
                    """
                    SELECT role FROM tenant_memberships
                    WHERE tenant_id = %s AND identity_id = %s AND status = 'active'
                    """,
                    (tenant_id, subject_id),
                ).fetchone()
                if identity is None or not identity[0]:
                    raise PermissionError("identity is inactive")
                if tenant is None or tenant[0] != "active":
                    raise PermissionError("tenant is inactive")
                if membership is None:
                    raise PermissionError("active tenant membership required")
                if expected_role is not None and membership[0] != expected_role:
                    raise PermissionError("membership role changed; re-authentication required")
                if expected_branch_ids is not None and expected_role in {"branch_manager", "employee"}:
                    rows = connection.execute(
                        """
                        SELECT bm.branch_id
                        FROM branch_memberships AS bm
                        JOIN branches AS b
                          ON b.tenant_id = bm.tenant_id
                         AND b.id = bm.branch_id
                         AND b.status = 'active'
                        WHERE bm.tenant_id = %s
                          AND bm.identity_id = %s
                          AND bm.status = 'active'
                        """,
                        (tenant_id, subject_id),
                    ).fetchall()
                    current_branches = frozenset(str(row[0]) for row in rows)
                    if current_branches != expected_branch_ids:
                        raise PermissionError("branch membership changed; re-authentication required")
            yield connection
