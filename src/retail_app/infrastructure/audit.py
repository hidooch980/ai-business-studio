"""Append-only business audit writer."""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4


def record_audit(
    connection: Any,
    *,
    tenant_id: str,
    actor_identity_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str,
    request_id: str | None = None,
    details: dict[str, object] | None = None,
) -> str:
    """Insert an audit record in the caller's transaction; never commits itself."""
    if outcome not in {"success", "denied", "failure"}:
        raise ValueError("invalid audit outcome")
    if not action.strip() or not resource_type.strip():
        raise ValueError("audit action and resource_type are required")
    event_id = str(uuid4())
    connection.execute(
        """
        INSERT INTO audit_events
            (id, tenant_id, actor_identity_id, action, resource_type,
             resource_id, outcome, request_id, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            event_id, tenant_id, actor_identity_id, action, resource_type,
            resource_id, outcome, request_id,
            json.dumps(details or {}, separators=(",", ":"), sort_keys=True),
        ),
    )
    return event_id
