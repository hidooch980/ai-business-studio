"""Canonical request hashing and tenant-scoped idempotency operations."""
from __future__ import annotations

import hashlib
import json
from typing import Any


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for a different request body."""


class IdempotencyInProgress(RuntimeError):
    """The same operation is already being processed."""


def request_digest(payload: object) -> bytes:
    """Hash canonical JSON so key reuse can be checked independent of key order."""
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def reserve_idempotency(
    connection: Any,
    *,
    tenant_id: str,
    operation: str,
    key: str,
    payload: object,
) -> dict[str, object] | None:
    """Reserve a key or return the stored response; caller owns the transaction.

    Concurrent requests serialize on the unique key. A conflicting payload is
    rejected, and completed requests replay the original response.
    """
    if not key or not 8 <= len(key) <= 200:
        raise ValueError("idempotency key must contain 8 to 200 characters")
    digest = request_digest(payload)
    result = connection.execute(
        """
        INSERT INTO idempotency_records
            (id, tenant_id, operation, idempotency_key, request_sha256, state)
        VALUES (gen_random_uuid(), %s, %s, %s, %s, 'processing')
        ON CONFLICT (tenant_id, operation, idempotency_key) DO NOTHING
        RETURNING id
        """,
        (tenant_id, operation, key, digest),
    )
    inserted = result.fetchone()
    if inserted:
        return None

    existing = connection.execute(
        """
        SELECT request_sha256, state, response_status, response_body
        FROM idempotency_records
        WHERE tenant_id = %s AND operation = %s AND idempotency_key = %s
        FOR UPDATE
        """,
        (tenant_id, operation, key),
    ).fetchone()
    if existing is None:
        raise RuntimeError("idempotency reservation disappeared")
    old_digest, state, status, body = existing
    if bytes(old_digest) != digest:
        raise IdempotencyConflict("idempotency key was already used with another request")
    if state == "completed":
        return {"status": status, "body": body}
    raise IdempotencyInProgress("the original request has not completed")


def complete_idempotency(
    connection: Any,
    *,
    tenant_id: str,
    operation: str,
    key: str,
    status: int,
    body: dict[str, object],
) -> None:
    if not 100 <= status <= 599:
        raise ValueError("invalid HTTP status")
    result = connection.execute(
        """
        UPDATE idempotency_records
        SET state = 'completed', response_status = %s, response_body = %s::jsonb,
            updated_at = now()
        WHERE tenant_id = %s AND operation = %s AND idempotency_key = %s
          AND state = 'processing'
        """,
        (
            status, json.dumps(body, separators=(",", ":"), sort_keys=True),
            tenant_id, operation, key,
        ),
    )
    if getattr(result, "rowcount", 1) != 1:
        raise RuntimeError("no processing idempotency record to complete")
