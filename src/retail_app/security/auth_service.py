"""OTP login and opaque rotating session lifecycle.

Delivery is injected by the host. No OTP is returned to clients or logged.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from uuid import UUID, uuid4

from fastapi import HTTPException

from retail_app.infrastructure.database import PostgresDatabase
from retail_app.security.authorization import AccessContext, Role


class OTPDelivery:
    """Small synchronous delivery contract implemented by an SMS/email provider."""

    def send(self, *, channel: str, destination: str, code: str) -> None:
        raise NotImplementedError


class AuthService:
    """Database-backed OTP and session operations; secrets are supplied by host."""

    def __init__(
        self,
        database: PostgresDatabase,
        *,
        otp_hmac_secret: bytes,
        otp_delivery: OTPDelivery,
        session_ttl_seconds: int = 60 * 60 * 24 * 30,
    ) -> None:
        if len(otp_hmac_secret) < 32:
            raise ValueError("OTP_HMAC_SECRET must contain at least 32 bytes")
        if not 300 <= session_ttl_seconds <= 60 * 60 * 24 * 90:
            raise ValueError("session TTL must be between 5 minutes and 90 days")
        self._database = database
        self._secret = otp_hmac_secret
        self._delivery = otp_delivery
        self._session_ttl_seconds = session_ttl_seconds

    def _fingerprint(self, identifier: str) -> bytes:
        normalized = identifier.strip().lower()
        return hmac.new(self._secret, b"identifier:" + normalized.encode(), hashlib.sha256).digest()

    def _code_hmac(self, challenge_id: UUID, code: str) -> bytes:
        return hmac.new(
            self._secret,
            b"otp:" + challenge_id.bytes + b":" + code.encode("ascii"),
            hashlib.sha256,
        ).digest()

    def request_otp(self, identifier: str) -> UUID:
        identifier = identifier.strip()
        if not 5 <= len(identifier) <= 254 or any(ch.isspace() for ch in identifier):
            raise HTTPException(status_code=400, detail="invalid identifier")
        channel = "sms" if identifier.startswith("+") else "email"
        if channel == "sms" and (not identifier[1:].isdigit() or not 8 <= len(identifier[1:]) <= 15):
            raise HTTPException(status_code=400, detail="invalid identifier")

        challenge_id = uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        fingerprint = self._fingerprint(identifier)
        code_hmac = self._code_hmac(challenge_id, code)
        with self._database.transaction() as connection:
            destination = connection.execute(
                "SELECT public.issue_auth_otp(%s, %s, %s, %s, %s)",
                (challenge_id, identifier, fingerprint, code_hmac, channel),
            ).fetchone()[0]

        # The API response is identical for existing and unknown identifiers.
        # Delivery failures are surfaced only as a generic service failure.
        if destination:
            try:
                self._delivery.send(channel=channel, destination=destination, code=code)
            except Exception as exc:
                raise HTTPException(status_code=503, detail="OTP delivery unavailable") from exc
        return challenge_id

    def verify_otp(self, *, challenge_id: UUID, identifier: str, code: str, tenant_id: str) -> tuple[str, str]:
        if not code.isascii() or not code.isdigit() or len(code) != 6:
            raise HTTPException(status_code=401, detail="invalid or expired challenge")
        fingerprint = self._fingerprint(identifier)
        with self._database.transaction() as connection:
            identity_id = connection.execute(
                "SELECT public.consume_auth_otp(%s, %s, %s)",
                (challenge_id, fingerprint, self._code_hmac(challenge_id, code)),
            ).fetchone()[0]
        if identity_id is None:
            raise HTTPException(status_code=401, detail="invalid or expired challenge")

        # The client may select a tenant, but it is trusted only after this
        # transaction confirms an active membership for the OTP-verified identity.
        with self._database.tenant_transaction(tenant_id=tenant_id, subject_id=str(identity_id)) as connection:
            membership = connection.execute(
                """
                SELECT i.is_active, t.status, tm.role
                FROM public.identities AS i
                JOIN public.tenant_memberships AS tm ON tm.identity_id = i.id
                JOIN public.tenants AS t ON t.id = tm.tenant_id
                WHERE i.id = %s AND tm.tenant_id = %s AND tm.status = 'active'
                """,
                (identity_id, tenant_id),
            ).fetchone()
            if membership is None or not membership[0] or membership[1] != "active":
                raise HTTPException(status_code=401, detail="invalid or expired challenge")
            try:
                Role(membership[2])
            except ValueError as exc:
                raise HTTPException(status_code=403, detail="unsupported membership role") from exc

            raw_token = secrets.token_urlsafe(48)
            csrf_token = secrets.token_urlsafe(32)
            connection.execute(
                """
                INSERT INTO public.auth_sessions
                    (id, tenant_id, identity_id, refresh_token_hash, csrf_token_hash, expires_at)
                VALUES (%s, %s, %s, %s, %s, clock_timestamp() + (%s * interval '1 second'))
                """,
                (
                    uuid4(), tenant_id, identity_id,
                    hashlib.sha256(raw_token.encode()).digest(),
                    hashlib.sha256(csrf_token.encode()).digest(),
                    self._session_ttl_seconds,
                ),
            )
            connection.execute(
                """
                INSERT INTO public.security_audit_events
                    (id, tenant_id, actor_identity_id, event_type, outcome, subject_identity_id)
                VALUES (%s, %s, %s, 'auth.otp.login', 'success', %s)
                """,
                (uuid4(), tenant_id, identity_id, identity_id),
            )
        return raw_token, csrf_token

    def rotate_session(self, context: AccessContext, session_id: str) -> tuple[str, str]:
        raw_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        new_session_id = uuid4()
        with self._database.tenant_transaction(
            tenant_id=context.tenant_id, subject_id=context.subject_id
        ) as connection:
            revoked = connection.execute(
                """
                UPDATE public.auth_sessions
                SET revoked_at = clock_timestamp()
                WHERE id = %s AND tenant_id = %s AND identity_id = %s
                  AND revoked_at IS NULL AND expires_at > clock_timestamp()
                RETURNING id
                """,
                (session_id, context.tenant_id, context.subject_id),
            ).fetchone()
            if revoked is None:
                raise HTTPException(status_code=401, detail="authentication required")
            connection.execute(
                """
                INSERT INTO public.auth_sessions
                    (id, tenant_id, identity_id, refresh_token_hash, csrf_token_hash,
                     expires_at, rotated_from_session_id)
                VALUES (%s, %s, %s, %s, %s,
                        clock_timestamp() + (%s * interval '1 second'), %s)
                """,
                (
                    new_session_id, context.tenant_id, context.subject_id,
                    hashlib.sha256(raw_token.encode()).digest(),
                    hashlib.sha256(csrf_token.encode()).digest(),
                    self._session_ttl_seconds, session_id,
                ),
            )
        return raw_token, csrf_token

    def revoke_session(self, context: AccessContext, session_id: str) -> None:
        with self._database.tenant_transaction(
            tenant_id=context.tenant_id, subject_id=context.subject_id
        ) as connection:
            connection.execute(
                """
                UPDATE public.auth_sessions SET revoked_at = clock_timestamp()
                WHERE id = %s AND tenant_id = %s AND identity_id = %s
                  AND revoked_at IS NULL
                """,
                (session_id, context.tenant_id, context.subject_id),
            )
