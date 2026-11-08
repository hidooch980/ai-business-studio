"""Provider-agnostic OTP challenge orchestration.

Persistence and distributed throttling are explicit ports: production must inject
transactional PostgreSQL and shared rate-limit implementations. This module never
logs or returns plaintext OTP values.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4


class OTPError(Exception):
    """Base class for safe OTP service errors."""


class OTPUnavailable(OTPError):
    """Raised when security configuration or a required dependency is absent."""


class OTPRejected(OTPError):
    """Raised for invalid, expired, consumed, or purpose-mismatched challenges."""


class OTPChannel(StrEnum):
    SMS = "sms"
    EMAIL = "email"


class OTPPurpose(StrEnum):
    LOGIN = "login"
    IDENTIFIER_VERIFY = "identifier_verify"
    RECOVERY = "recovery"
    STEP_UP = "step_up"


@dataclass(frozen=True, slots=True)
class OTPConfig:
    code_pepper: bytes
    identifier_pepper: bytes
    ttl: timedelta = timedelta(minutes=5)
    resend_cooldown: timedelta = timedelta(seconds=60)
    max_attempts: int = 5
    code_digits: int = 6

    def __post_init__(self) -> None:
        if len(self.code_pepper) < 32 or len(self.identifier_pepper) < 32:
            raise OTPUnavailable("OTP peppers must each contain at least 32 bytes")
        if self.ttl <= timedelta(0) or self.resend_cooldown < timedelta(0):
            raise ValueError("invalid OTP timing configuration")
        if self.max_attempts != 5 or self.code_digits != 6:
            raise ValueError("the initial policy requires six digits and five attempts")


@dataclass(frozen=True, slots=True)
class OTPChallenge:
    id: UUID
    identifier_fingerprint: bytes
    code_hmac: bytes
    purpose: OTPPurpose
    channel: OTPChannel
    created_at: datetime
    expires_at: datetime
    resend_after: datetime


class OTPRepository(Protocol):
    """A production adapter must implement these operations transactionally."""

    def create_challenge(self, challenge: OTPChallenge) -> None:
        """Atomically invalidate prior active challenge(s) and insert this one."""

    def invalidate_challenge(self, challenge_id: UUID, at: datetime) -> None:
        """Invalidate a challenge, e.g. after a delivery failure."""

    def verify_and_consume(
        self,
        challenge_id: UUID,
        candidate_hmac: bytes,
        purpose: OTPPurpose,
        at: datetime,
        max_attempts: int,
    ) -> bool:
        """Lock row, check purpose/expiry/attempts, compare HMAC and consume once."""


class OTPDeliveryProvider(Protocol):
    def send(self, destination: str, channel: OTPChannel, code: str) -> None:
        """Deliver the code. Implementations must not log the code or destination."""


class OTPRateLimiter(Protocol):
    def allow(self, keys: tuple[str, ...], at: datetime) -> bool:
        """Atomically enforce all supplied limits across app instances."""


@dataclass(frozen=True, slots=True)
class OTPReceipt:
    challenge_id: UUID
    message: str
    expires_at: datetime
    resend_after: datetime


def normalize_identifier(identifier: str, channel: OTPChannel) -> str:
    value = identifier.strip()
    if channel is OTPChannel.SMS:
        normalized = re.sub(r"[\\s().-]", "", value)
        if not re.fullmatch(r"\\+[1-9][0-9]{7,14}", normalized):
            raise ValueError("phone number must be in E.164 format")
        return normalized
    normalized = value.lower()
    if len(normalized) > 254 or not re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", normalized):
        raise ValueError("invalid email address")
    return normalized


class OTPService:
    """Secure OTP orchestration; requires real persistence, delivery and throttling ports."""

    GENERIC_MESSAGE = "If the identifier is eligible, a verification code will be sent."

    def __init__(
        self,
        config: OTPConfig,
        repository: OTPRepository,
        delivery: OTPDeliveryProvider,
        rate_limiter: OTPRateLimiter,
    ) -> None:
        if not all((repository, delivery, rate_limiter)):
            raise OTPUnavailable("OTP persistence, delivery and rate limiting are required")
        self._config = config
        self._repository = repository
        self._delivery = delivery
        self._rate_limiter = rate_limiter

    def _fingerprint(self, identifier: str) -> bytes:
        return hmac.new(
            self._config.identifier_pepper, identifier.encode("utf-8"), hashlib.sha256
        ).digest()

    def _code_hmac(self, challenge_id: UUID, purpose: OTPPurpose, code: str) -> bytes:
        message = f"{challenge_id}:{purpose.value}:{code}".encode("ascii")
        return hmac.new(self._config.code_pepper, message, hashlib.sha256).digest()

    def request_code(
        self,
        identifier: str,
        channel: OTPChannel,
        purpose: OTPPurpose,
        *,
        rate_limit_keys: tuple[str, ...],
        now: datetime | None = None,
    ) -> OTPReceipt:
        at = now or datetime.now(UTC)
        if at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        normalized = normalize_identifier(identifier, channel)
        fingerprint = self._fingerprint(normalized)
        keys = tuple(dict.fromkeys((*rate_limit_keys, f"identifier:{fingerprint.hex()}")))
        if not rate_limit_keys or not self._rate_limiter.allow(keys, at):
            raise OTPRejected("request temporarily unavailable")

        code = f"{secrets.randbelow(10**self._config.code_digits):0{self._config.code_digits}d}"
        challenge_id = uuid4()
        challenge = OTPChallenge(
            id=challenge_id,
            identifier_fingerprint=fingerprint,
            code_hmac=self._code_hmac(challenge_id, purpose, code),
            purpose=purpose,
            channel=channel,
            created_at=at,
            expires_at=at + self._config.ttl,
            resend_after=at + self._config.resend_cooldown,
        )
        self._repository.create_challenge(challenge)
        try:
            self._delivery.send(normalized, channel, code)
        except Exception as exc:
            self._repository.invalidate_challenge(challenge_id, at)
            raise OTPUnavailable("verification delivery unavailable") from exc
        return OTPReceipt(
            challenge_id=challenge_id,
            message=self.GENERIC_MESSAGE,
            expires_at=challenge.expires_at,
            resend_after=challenge.resend_after,
        )

    def verify_code(
        self,
        challenge_id: UUID,
        code: str,
        purpose: OTPPurpose,
        *,
        rate_limit_keys: tuple[str, ...],
        now: datetime | None = None,
    ) -> None:
        at = now or datetime.now(UTC)
        if at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if not rate_limit_keys or not self._rate_limiter.allow(
            tuple(dict.fromkeys((*rate_limit_keys, f"challenge:{challenge_id}"))), at
        ):
            raise OTPRejected("verification rejected")
        if not re.fullmatch(r"[0-9]{6}", code):
            raise OTPRejected("verification rejected")
        candidate = self._code_hmac(challenge_id, purpose, code)
        if not self._repository.verify_and_consume(
            challenge_id, candidate, purpose, at, self._config.max_attempts
        ):
            raise OTPRejected("verification rejected")
