"""Opaque server-side session issuance, rotation, replay detection and logout."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
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


def _valid_token(token: str) -> bool:
    return (
        isinstance(token, str)
        and 32 <= len(token) <= 512
        and token.isascii()
        and all(character.isalnum() or character in "_-" for character in token)
    )


def _digest(token: str) -> bytes:
    if not _valid_token(token):
        raise SessionAuthenticationError("invalid session")
    return hashlib.sha256(token.encode("ascii")).digest()


def _record_security_event(
    connection: Any,
    *,
    tenant_id: str,
    subject_id: str,
    event_type: str,
    outcome: str,
    metadata: dict[str, object] | None = None,
) -> None:
    connection.execute(
        """INSERT INTO security_audit_events
           (id, tenant_id, actor_identity_id, event_type, outcome,
            subject_identity_id, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (
            str(uuid4()), tenant_id, subject_id, event_type, outcome,
            subject_id, json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
        ),
    )


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
            database_now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
            expires_at = database_now + self.lifetime
            connection.execute(
                """INSERT INTO auth_sessions
                   (id, tenant_id, identity_id, refresh_token_hash, expires_at, token_family_id)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (session_id, tenant_id, subject_id, _digest(token), expires_at, family_id),
            )
            _record_security_event(
                connection, tenant_id=tenant_id, subject_id=subject_id,
                event_type="session.issued", outcome="success",
                metadata={"session_id": session_id},
            )
        return IssuedSession(session_id, token, expires_at)

    def rotate(self, token: str) -> IssuedSession:
        """Atomically consume one token and issue its successor; reuse revokes its family."""
        if not _valid_token(token):
            raise SessionAuthenticationError("invalid session")
        presented_hash = _digest(token)
        new_token = secrets.token_urlsafe(48)
        new_id = str(uuid4())
        failure: str | None = None
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
            database_now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
            if revoked_at is not None:
                connection.execute(
                    """UPDATE auth_sessions SET revoked_at = COALESCE(revoked_at, statement_timestamp())
                       WHERE token_family_id = %s AND revoked_at IS NULL""",
                    (family_id,),
                )
                failure = "replay"
            elif expires_at <= database_now:
                connection.execute(
                    """UPDATE auth_sessions SET revoked_at = COALESCE(revoked_at, statement_timestamp())
                       WHERE token_family_id = %s AND revoked_at IS NULL""",
                    (family_id,),
                )
                failure = "expired"
            else:
                new_expiry = database_now + self.lifetime
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
                    failure = "membership_revoked"
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
            if failure is not None:
                _record_security_event(
                    connection, tenant_id=tenant_id, subject_id=subject_id,
                    event_type={
                        "replay": "session.refresh_replay_detected",
                        "expired": "session.refresh_expired",
                        "membership_revoked": "session.refresh_denied",
                    }[failure],
                    outcome="denied",
                    metadata={"session_id": old_id, "reason": failure},
                )
            elif issued is not None:
                _record_security_event(
                    connection, tenant_id=tenant_id, subject_id=subject_id,
                    event_type="session.refresh_rotated", outcome="success",
                    metadata={"old_session_id": old_id, "new_session_id": new_id},
                )

        if failure == "replay":
            raise RefreshTokenReplayError("refresh token reuse detected; session family revoked")
        if failure is not None or issued is None:
            raise SessionAuthenticationError("session is expired, revoked or no longer authorized")
        return issued

    def revoke(self, token: str) -> bool:
        """Revoke the presented session; unknown tokens are a harmless no-op."""
        if not _valid_token(token):
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
            if result.rowcount == 1:
                _record_security_event(
                    connection, tenant_id=tenant_id, subject_id=subject_id,
                    event_type="session.revoked", outcome="success",
                    metadata={"session_id": str(session_id)},
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
            if result.rowcount:
                _record_security_event(
                    connection, tenant_id=tenant_id, subject_id=subject_id,
                    event_type="session.revoke_all", outcome="success",
                    metadata={"revoked_count": result.rowcount},
                )
            return result.rowcount
