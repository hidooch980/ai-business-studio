"""Opaque server-side session issuance, rotation, replay detection and logout."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4


class SessionAuthenticationError(PermissionError):
    """Presented session credential is invalid, expired or revoked."""


class RefreshTokenReplayError(SessionAuthenticationError):
    """A rotated or revoked refresh token was presented again."""


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session_id: str
    refresh_token: str
    expires_at: datetime


def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


class SessionService:
    """Database-backed session lifecycle; callers must authenticate before issue()."""

    def __init__(self, database: Any, *, lifetime: timedelta = timedelta(days=30)) -> None:
        if lifetime <= timedelta(0) or lifetime > timedelta(days=90):
            raise ValueError("session lifetime must be between 1 second and 90 days")
        self.database = database
        self.lifetime = lifetime

    def issue(self, *, tenant_id: str, subject_id: str) -> IssuedSession:
        """Issue only after the caller has independently verified the identity."""
        token = secrets.token_urlsafe(48)
        session_id = str(uuid4())
        family_id = session_id
        expires_at = datetime.now(UTC) + self.lifetime
        with self.database.transaction() as connection:
            connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            connection.execute("SELECT set_config('app.subject_id', %s, true)", (subject_id,))
            identity = connection.execute(
                "SELECT is_active FROM identities WHERE id = %s FOR SHARE", (subject_id,)
            ).fetchone()
            membership = connection.execute(
                """SELECT 1 FROM tenant_memberships
                   WHERE tenant_id = %s AND identity_id = %s AND status = 'active' FOR SHARE""",
                (tenant_id, subject_id),
            ).fetchone()
            tenant = connection.execute(
                "SELECT 1 FROM tenants WHERE id = %s AND status = 'active' FOR SHARE",
                (tenant_id,),
            ).fetchone()
            if identity is None or not identity[0] or membership is None or tenant is None:
                raise SessionAuthenticationError("active identity and membership required")
            connection.execute(
                """INSERT INTO auth_sessions
                   (id, tenant_id, identity_id, refresh_token_hash, expires_at, token_family_id)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (session_id, tenant_id, subject_id, _digest(token), expires_at, family_id),
            )
        return IssuedSession(session_id, token, expires_at)

    def rotate(self, token: str) -> IssuedSession:
        """Atomically consume one token and issue its successor; reuse revokes its family."""
        if not token or len(token) > 512:
            raise SessionAuthenticationError("invalid session")
        presented_hash = _digest(token)
        new_token = secrets.token_urlsafe(48)
        new_id = str(uuid4())
        now = datetime.now(UTC)
        new_expiry = now + self.lifetime
        replay = False
        issued: IssuedSession | None = None

        with self.database.transaction() as connection:
            bootstrap = connection.execute(
                """SELECT tenant_id, identity_id, session_id
                   FROM resolve_auth_session_bootstrap(%s)""",
                (presented_hash,),
            ).fetchone()
            if bootstrap is None:
                raise SessionAuthenticationError("invalid session")
            tenant_id, subject_id, old_id = map(str, bootstrap)
            connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            connection.execute("SELECT set_config('app.subject_id', %s, true)", (subject_id,))
            old = connection.execute(
                """SELECT token_family_id, revoked_at, expires_at
                   FROM auth_sessions
                   WHERE id = %s AND tenant_id = %s AND identity_id = %s
                     AND refresh_token_hash = %s
                   FOR UPDATE""",
                (old_id, tenant_id, subject_id, presented_hash),
            ).fetchone()
            if old is None:
                raise SessionAuthenticationError("invalid session")
            family_id, revoked_at, expires_at = old
            if revoked_at is not None or expires_at <= now:
                connection.execute(
                    """UPDATE auth_sessions SET revoked_at = COALESCE(revoked_at, statement_timestamp())
                       WHERE token_family_id = %s AND revoked_at IS NULL""",
                    (family_id,),
                )
                replay = revoked_at is not None
            else:
                identity = connection.execute(
                    "SELECT is_active FROM identities WHERE id = %s FOR SHARE", (subject_id,)
                ).fetchone()
                membership = connection.execute(
                    """SELECT 1 FROM tenant_memberships
                       WHERE tenant_id = %s AND identity_id = %s AND status = 'active' FOR SHARE""",
                    (tenant_id, subject_id),
                ).fetchone()
                tenant = connection.execute(
                    "SELECT 1 FROM tenants WHERE id = %s AND status = 'active' FOR SHARE",
                    (tenant_id,),
                ).fetchone()
                if identity is None or not identity[0] or membership is None or tenant is None:
                    connection.execute(
                        """UPDATE auth_sessions SET revoked_at = COALESCE(revoked_at, statement_timestamp())
                           WHERE token_family_id = %s AND revoked_at IS NULL""",
                        (family_id,),
                    )
                    replay = True
                else:
                    connection.execute(
                        """UPDATE auth_sessions SET revoked_at = statement_timestamp(),
                           last_seen_at = statement_timestamp()
                           WHERE id = %s AND revoked_at IS NULL""",
                        (old_id,),
                    )
                    connection.execute(
                        """INSERT INTO auth_sessions
                           (id, tenant_id, identity_id, refresh_token_hash, expires_at,
                            rotated_from_session_id, token_family_id)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (new_id, tenant_id, subject_id, _digest(new_token), new_expiry, old_id, family_id),
                    )
                    issued = IssuedSession(new_id, new_token, new_expiry)

        if replay:
            raise RefreshTokenReplayError("refresh token reuse detected; session family revoked")
        if issued is None:
            raise SessionAuthenticationError("invalid session")
        return issued

    def revoke(self, token: str) -> bool:
        """Revoke the presented session; unknown tokens are a harmless no-op."""
        if not token or len(token) > 512:
            return False
        digest = _digest(token)
        with self.database.transaction() as connection:
            bootstrap = connection.execute(
                """SELECT tenant_id, identity_id, session_id
                   FROM resolve_auth_session_bootstrap(%s)""",
                (digest,),
            ).fetchone()
            if bootstrap is None:
                return False
            tenant_id, subject_id, session_id = map(str, bootstrap)
            connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            connection.execute("SELECT set_config('app.subject_id', %s, true)", (subject_id,))
            result = connection.execute(
                """UPDATE auth_sessions SET revoked_at = COALESCE(revoked_at, statement_timestamp())
                   WHERE id = %s AND tenant_id = %s AND identity_id = %s
                     AND refresh_token_hash = %s AND revoked_at IS NULL""",
                (session_id, tenant_id, subject_id, digest),
            )
            return result.rowcount == 1

    def revoke_all(self, *, tenant_id: str, subject_id: str) -> int:
        """Revoke every active session for a previously authenticated subject."""
        with self.database.transaction() as connection:
            connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            connection.execute("SELECT set_config('app.subject_id', %s, true)", (subject_id,))
            result = connection.execute(
                """UPDATE auth_sessions SET revoked_at = statement_timestamp()
                   WHERE tenant_id = %s AND identity_id = %s AND revoked_at IS NULL""",
                (tenant_id, subject_id),
            )
            return result.rowcount
