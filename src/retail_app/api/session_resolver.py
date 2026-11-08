"""Resolve an opaque browser session into a DB-backed, deny-by-default context."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

from retail_app.security.authorization import AccessContext, Role

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,512}$")


@dataclass(frozen=True, slots=True)
class SessionCookieSettings:
    name: str = "__Host-retail_session"
    secure: bool = True
    httponly: bool = True
    samesite: str = "strict"
    path: str = "/"

    def validate(self) -> None:
        if not self.name or self.path != "/" or self.samesite.lower() != "strict" or not self.httponly:
            raise ValueError("session cookies require HttpOnly, SameSite=Strict and Path=/")
        if self.name.startswith("__Host-") and (not self.secure or self.path != "/"):
            raise ValueError("__Host- cookies require Secure and Path=/")


class PostgresSessionResolver:
    """FastAPI dependency; all identity, tenant, role and branch facts come from PostgreSQL.

    The bootstrap SECURITY DEFINER function returns only identifiers. The normal
    auth_sessions/identities/tenants/membership RLS policies are then applied in
    the same transaction after transaction-local tenant and subject are set.
    """

    def __init__(self, database: Any, settings: SessionCookieSettings | None = None) -> None:
        self.database = database
        self.settings = settings or SessionCookieSettings()
        self.settings.validate()

    def __call__(self, request: Request) -> AccessContext:
        token = request.cookies.get(self.settings.name)
        if token is None or not _TOKEN_RE.fullmatch(token):
            raise HTTPException(status_code=401, detail="authentication required")

        token_hash = hashlib.sha256(token.encode("ascii")).digest()
        try:
            with self.database.transaction() as connection:
                bootstrap = connection.execute(
                    """
                    SELECT tenant_id, identity_id, session_id
                    FROM resolve_auth_session_bootstrap(%s)
                    """,
                    (token_hash,),
                ).fetchone()
                if bootstrap is None:
                    raise HTTPException(status_code=401, detail="invalid or expired session")

                tenant_id, subject_id, session_id = map(str, bootstrap)
                connection.execute(
                    "SELECT set_config('app.tenant_id', %s, true)", (tenant_id,)
                )
                connection.execute(
                    "SELECT set_config('app.subject_id', %s, true)", (subject_id,)
                )

                session = connection.execute(
                    """
                    SELECT id
                    FROM auth_sessions
                    WHERE id = %s AND tenant_id = %s AND identity_id = %s
                      AND refresh_token_hash = %s
                      AND revoked_at IS NULL AND expires_at > statement_timestamp()
                    """,
                    (session_id, tenant_id, subject_id, token_hash),
                ).fetchone()
                if session is None:
                    raise HTTPException(status_code=401, detail="invalid or expired session")

                identity = connection.execute(
                    "SELECT is_active FROM identities WHERE id = %s",
                    (subject_id,),
                ).fetchone()
                if identity is None or not identity[0]:
                    raise HTTPException(status_code=401, detail="identity is inactive")

                tenant = connection.execute(
                    "SELECT status FROM tenants WHERE id = %s",
                    (tenant_id,),
                ).fetchone()
                if tenant is None or tenant[0] != "active":
                    raise HTTPException(status_code=403, detail="tenant is inactive")

                membership = connection.execute(
                    """
                    SELECT role
                    FROM tenant_memberships
                    WHERE tenant_id = %s AND identity_id = %s AND status = 'active'
                    """,
                    (tenant_id, subject_id),
                ).fetchone()
                if membership is None:
                    raise HTTPException(status_code=403, detail="active tenant membership required")
                try:
                    role = Role(membership[0])
                except ValueError as exc:
                    raise HTTPException(status_code=403, detail="unsupported membership role") from exc

                branches = connection.execute(
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
                    ORDER BY bm.branch_id
                    """,
                    (tenant_id, subject_id),
                ).fetchall()
                branch_ids = frozenset(str(row[0]) for row in branches)

                return AccessContext(
                    subject_id=subject_id,
                    tenant_id=tenant_id,
                    role=role,
                    branch_ids=branch_ids,
                    active=True,
                    session_id=session_id,
                    session_token_hash=token_hash,
                )
        except HTTPException:
            raise
        except Exception as exc:
            # Fail closed on database errors; never leak driver/SQL details to clients.
            raise HTTPException(status_code=503, detail="authentication service unavailable") from exc
