"""Transactional domain-event and outbox writer."""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4


def append_domain_event(
    connection: Any,
    *,
    tenant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    event_type: str,
    payload: dict[str, object],
    destination: str,
    metadata: dict[str, object] | None = None,
) -> tuple[str, str]:
    """Atomically append an immutable event and its outbox delivery record."""
    if aggregate_version < 1:
        raise ValueError("aggregate_version must be positive")
    if not all(value.strip() for value in (aggregate_type, event_type, destination)):
        raise ValueError("aggregate_type, event_type and destination are required")
    event_id, outbox_id = str(uuid4()), str(uuid4())
    connection.execute(
        """
        INSERT INTO domain_events
            (id, tenant_id, aggregate_type, aggregate_id, aggregate_version,
             event_type, payload, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
        """,
        (
            event_id, tenant_id, aggregate_type, aggregate_id, aggregate_version,
            event_type, json.dumps(payload, separators=(",", ":"), sort_keys=True),
            json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
        ),
    )
    connection.execute(
        """
        INSERT INTO outbox_messages (id, tenant_id, event_id, destination)
        VALUES (%s, %s, %s, %s)
        """,
        (outbox_id, tenant_id, event_id, destination),
    )
    return event_id, outbox_id
