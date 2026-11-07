from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from backend.app.outbox.models import OutboxEvent
from backend.app.outbox.service import claim_outbox_events, mark_outbox_delivered, retry_outbox_event


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    id: UUID
    tenant_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict
    attempts: int
    lease_token: UUID


OutboxHandler = Callable[[Session, OutboxMessage], None]


def run_outbox_batch(
    session_factory: sessionmaker[Session],
    *,
    worker_id: str,
    handlers: dict[str, OutboxHandler],
    limit: int = 50,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 30,
    max_attempts: int = 8,
) -> dict[str, int]:
    """Deliver one leased batch using at-least-once semantics.

    Handlers must be idempotent and must not perform irreversible work before
    validating the message. Database changes made by a handler are committed
    together with the delivery acknowledgement.
    """
    with session_factory() as claim_session:
        claimed = claim_outbox_events(
            claim_session,
            worker_id=worker_id,
            limit=limit,
            lease_seconds=lease_seconds,
        )
        messages = [
            OutboxMessage(
                id=event.id,
                tenant_id=event.tenant_id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                payload=dict(event.payload),
                attempts=event.attempts,
                lease_token=event.lease_token,
            )
            for event in claimed
            if event.lease_token is not None
        ]

    result = {"claimed": len(messages), "delivered": 0, "retried": 0, "dead_letter": 0}
    for message in messages:
        handler = handlers.get(message.event_type)
        with session_factory() as db:
            try:
                if handler is None:
                    raise LookupError(f"No handler registered for event type: {message.event_type}")
                handler(db, message)
                if mark_outbox_delivered(db, event_id=message.id, lease_token=message.lease_token):
                    result["delivered"] += 1
            except Exception as exc:
                if retry_outbox_event(
                    db,
                    event_id=message.id,
                    lease_token=message.lease_token,
                    error=f"{type(exc).__name__}: {exc}",
                    retry_delay_seconds=retry_delay_seconds,
                    max_attempts=max_attempts,
                ):
                    if message.attempts >= max_attempts:
                        result["dead_letter"] += 1
                    else:
                        result["retried"] += 1
    return result
