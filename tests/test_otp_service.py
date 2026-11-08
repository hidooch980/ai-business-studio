from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from retail_app.security.otp import (
    OTPChannel,
    OTPChallenge,
    OTPConfig,
    OTPPurpose,
    OTPRejected,
    OTPService,
    OTPUnavailable,
)


class MemoryRepository:
    def __init__(self):
        self.rows: dict[UUID, OTPChallenge] = {}
        self.consumed: set[UUID] = set()
        self.invalidated: set[UUID] = set()
        self.failures: dict[UUID, int] = {}

    def create_challenge(self, challenge):
        self.rows[challenge.id] = challenge

    def invalidate_challenge(self, challenge_id, at):
        self.invalidated.add(challenge_id)

    def verify_and_consume(self, challenge_id, candidate_hmac, purpose, at, max_attempts):
        row = self.rows.get(challenge_id)
        if (
            row is None or challenge_id in self.consumed or challenge_id in self.invalidated
            or row.purpose is not purpose or at >= row.expires_at
            or self.failures.get(challenge_id, 0) >= max_attempts
        ):
            return False
        if not hmac.compare_digest(row.code_hmac, candidate_hmac):
            self.failures[challenge_id] = self.failures.get(challenge_id, 0) + 1
            return False
        self.consumed.add(challenge_id)
        return True


class MemoryLimiter:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    def allow(self, keys, at):
        self.calls.append(keys)
        return self.allowed


class CaptureDelivery:
    def __init__(self, fail=False):
        self.code = None
        self.fail = fail

    def send(self, destination, channel, code):
        if self.fail:
            raise RuntimeError("provider down")
        self.code = code


@pytest.fixture
def service():
    repo, limiter, delivery = MemoryRepository(), MemoryLimiter(), CaptureDelivery()
    config = OTPConfig(b"a" * 32, b"b" * 32)
    return OTPService(config, repo, delivery, limiter), repo, limiter, delivery


def test_otp_is_six_digit_csprng_output_and_plaintext_not_in_receipt(service):
    svc, repo, _, delivery = service
    receipt = svc.request_code(
        "+1 (202) 555-0101", OTPChannel.SMS, OTPPurpose.LOGIN,
        rate_limit_keys=("ip:127.0.0.1",),
    )
    assert delivery.code is not None and len(delivery.code) == 6
    assert delivery.code.isdigit()
    assert receipt.message == OTPService.GENERIC_MESSAGE
    assert delivery.code not in repr(receipt)
    assert delivery.code.encode() not in repo.rows[receipt.challenge_id].code_hmac


def test_expired_challenge_is_rejected(service):
    svc, _, _, delivery = service
    now = datetime.now(UTC)
    receipt = svc.request_code(
        "+12025550101", OTPChannel.SMS, OTPPurpose.LOGIN,
        rate_limit_keys=("ip:test",), now=now,
    )
    with pytest.raises(OTPRejected):
        svc.verify_code(
            receipt.challenge_id, delivery.code, OTPPurpose.LOGIN,
            rate_limit_keys=("ip:test",), now=now + timedelta(minutes=6),
        )


def test_code_is_single_use(service):
    svc, _, _, delivery = service
    receipt = svc.request_code(
        "+12025550102", OTPChannel.SMS, OTPPurpose.LOGIN,
        rate_limit_keys=("ip:test",),
    )
    svc.verify_code(receipt.challenge_id, delivery.code, OTPPurpose.LOGIN, rate_limit_keys=("ip:test",))
    with pytest.raises(OTPRejected):
        svc.verify_code(receipt.challenge_id, delivery.code, OTPPurpose.LOGIN, rate_limit_keys=("ip:test",))


def test_wrong_purpose_is_rejected(service):
    svc, _, _, delivery = service
    receipt = svc.request_code(
        "+12025550103", OTPChannel.SMS, OTPPurpose.LOGIN,
        rate_limit_keys=("ip:test",),
    )
    with pytest.raises(OTPRejected):
        svc.verify_code(
            receipt.challenge_id, delivery.code, OTPPurpose.STEP_UP,
            rate_limit_keys=("ip:test",),
        )


def test_rate_limit_fails_closed(service):
    svc, _, limiter, _ = service
    limiter.allowed = False
    with pytest.raises(OTPRejected):
        svc.request_code(
            "+12025550104", OTPChannel.SMS, OTPPurpose.LOGIN,
            rate_limit_keys=("ip:test",),
        )


def test_delivery_failure_invalidates_persisted_challenge(service):
    svc, repo, _, delivery = service
    delivery.fail = True
    with pytest.raises(OTPUnavailable):
        svc.request_code(
            "+12025550105", OTPChannel.SMS, OTPPurpose.LOGIN,
            rate_limit_keys=("ip:test",),
        )
    assert len(repo.invalidated) == 1


def test_missing_or_weak_peppers_fail_closed():
    with pytest.raises(OTPUnavailable):
        OTPConfig(b"short", b"b" * 32)


def test_five_failed_attempts_block_later_correct_code(service):
    svc, repo, _, delivery = service
    receipt = svc.request_code(
        "+12025550106", OTPChannel.SMS, OTPPurpose.LOGIN,
        rate_limit_keys=("ip:test",),
    )
    for _ in range(5):
        with pytest.raises(OTPRejected):
            svc.verify_code(
                receipt.challenge_id, "000000", OTPPurpose.LOGIN,
                rate_limit_keys=("ip:test",),
            )
    with pytest.raises(OTPRejected):
        svc.verify_code(
            receipt.challenge_id, delivery.code, OTPPurpose.LOGIN,
            rate_limit_keys=("ip:test",),
        )
    assert repo.failures[receipt.challenge_id] == 5
