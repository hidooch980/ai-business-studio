"""PostgreSQL-backed session and membership resolver.

The raw opaque cookie token is hashed in-process. A narrowly privileged
SECURITY DEFINER function resolves only that hash before RLS context exists.
All identity, tenant, role and branch data is then read in a tenant-scoped
transaction under the ordinary runtime role.
"""
from __future__ import annotations

import hashlib
import re
from uuid import uuid4

from fastapi import HTTPException, Request

from retail_app.infrastructure.database import PostgresDatabase
from retail_app.security.authorization import AccessContext, Role


class SessionResolver:
    """Resolve a request cookie into a live AccessContext using PostgreSQL."""

    def __init__(
        self,
        database: PostgresDatabase,
        *,
        cookie_name: str = "__Host-retail_session",
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", cookie_name):
            raise ValueError("invalid session cookie name")
        self._database = database
        self._cookie_name = cookie_name

    def __call__(self, request: Request) -> AccessContext:
        token = request.cookies.get(self._cookie_name)
        if not token or len(token) < 32 or len(token) > 512:
            raise HTTPException(status_code=401, detail="authentication required")

        token_hash = hashlib.sha256(token.encode("utf-8")).digest()
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT session_id, tenant_id, identity_id "
                "FROM public.resolve_auth_session(%s)",
                (token_hash,),
            ).fetchone()

        if row is None:
            raise HTTPException(status_code=401, detail="authentication required")

        _, tenant_id, identity_id = row

        membership_denied = False
        branch_ids: frozenset[str] = frozenset()
        role: Role | None = None
        with self._database.tenant_transaction(
            tenant_id=str(tenant_id), subject_id=str(identity_id)
        ) as connection:
            membership = connection.execute(
                """
                SELECT i.is_active, t.status, tm.role
                FROM public.identities AS i
                JOIN public.tenant_memberships AS tm
                  ON tm.identity_id = i.id
                JOIN public.tenants AS t
                  ON t.id = tm.tenant_id
                WHERE i.id = %s
                  AND tm.tenant_id = %s
                  AND tm.status = 'active'
                """,
                (identity_id, tenant_id),
            ).fetchone()
            if membership is None or not membership[0] or membership[1] != "active":
                membership_denied = True
                connection.execute(
                    """
                    INSERT INTO public.security_audit_events
                        (id, tenant_id, actor_identity_id, event_type, outcome, subject_identity_id)
                    VALUES (%s, %s, %s, 'auth.session.denied', 'denied', %s)
                    """,
                    (uuid4(), tenant_id, identity_id, identity_id),
                )
            else:
                try:
                    role = Role(membership[2])
                except ValueError as exc:
                    raise HTTPException(status_code=403, detail="unsupported membership role") from exc

                branches = connection.execute(
                    """
                    SELECT bm.branch_id
                    FROM public.branch_memberships AS bm
                    JOIN public.branches AS b
                      ON b.tenant_id = bm.tenant_id AND b.id = bm.branch_id
                    WHERE bm.tenant_id = %s
                      AND bm.identity_id = %s
                      AND bm.status = 'active'
                      AND b.status = 'active'
                    ORDER BY bm.branch_id
                    """,
                    (tenant_id, identity_id),
                ).fetchall()
                branch_ids = frozenset(str(branch[0]) for branch in branches)
                connection.execute(
                    """
                    INSERT INTO public.security_audit_events
                        (id, tenant_id, actor_identity_id, event_type, outcome, subject_identity_id)
                    VALUES (%s, %s, %s, 'auth.session.resolved', 'success', %s)
                    """,
                    (uuid4(), tenant_id, identity_id, identity_id),
                )

        if membership_denied:
            raise HTTPException(status_code=401, detail="authentication required")
        assert role is not None

        return AccessContext(
            subject_id=str(identity_id),
            tenant_id=str(tenant_id),
            role=role,
            branch_ids=branch_ids,
            active=True,
        )
