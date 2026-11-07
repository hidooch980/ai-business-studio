from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from backend.app.outbox.models import OutboxEvent


def enqueue_outbox_event(
    db: Session,
    *,
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    dedupe_key: str,
    payload: dict,
) -> OutboxEvent:
    if not all(value.strip() for value in (event_type, aggregate_type, aggregate_id, dedupe_key)):
        raise ValueError("Outbox event identifiers cannot be blank")
    existing = db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        if (
            existing.event_type != event_type
            or existing.aggregate_type != aggregate_type
            or existing.aggregate_id != aggregate_id
            or existing.payload != payload
        ):
            raise ValueError("Outbox dedupe key was reused for a different event")
        return existing
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        dedupe_key=dedupe_key,
        payload=payload,
        status="pending",
        attempts=0,
        available_at=datetime.now(UTC),
    )
    db.add(event)
    db.flush()
    return event


def claim_outbox_events(
    db: Session,
    *,
    worker_id: str,
    limit: int = 50,
    lease_seconds: int = 60,
) -> list[OutboxEvent]:
    if not worker_id.strip() or len(worker_id) > 120:
        raise ValueError("worker_id must contain 1-120 non-whitespace characters")
    if not 1 <= limit <= 200 or not 5 <= lease_seconds <= 3600:
        raise ValueError("Invalid outbox claim limit or lease duration")
    now = datetime.now(UTC)
    lease_until = now + timedelta(seconds=lease_seconds)
    eligible = or_(
        (OutboxEvent.status == "pending") & (OutboxEvent.available_at <= now),
        (OutboxEvent.status == "processing") & (OutboxEvent.locked_until <= now),
    )
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        # One atomic UPDATE prevents two local workers from claiming the same rows.
        lease_token = uuid4()
        candidate_ids = (
            select(OutboxEvent.id)
            .where(eligible)
            .order_by(OutboxEvent.available_at, OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
        )
        statement = (
            update(OutboxEvent)
            .where(OutboxEvent.id.in_(candidate_ids))
            .values(
                status="processing",
                attempts=OutboxEvent.attempts + 1,
                locked_by=worker_id,
                locked_until=lease_until,
                lease_token=lease_token,
            )
            .returning(OutboxEvent)
        )
        events = db.scalars(statement).all()
    elif dialect == "postgresql":
        statement = (
            select(OutboxEvent)
            .where(eligible)
            .order_by(OutboxEvent.available_at, OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = db.scalars(statement).all()
        for event in events:
            event.status = "processing"
            event.attempts += 1
            event.locked_by = worker_id
            event.locked_until = lease_until
            event.lease_token = uuid4()
    else:
        raise RuntimeError("Outbox claiming requires SQLite or PostgreSQL")
    db.commit()
    return events

def mark_outbox_delivered(db: Session, *, event_id: UUID, lease_token: UUID) -> bool:
    event = db.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update())
    if event is None or event.status != "processing" or event.lease_token != lease_token:
        return False
    event.status = "delivered"
    event.delivered_at = datetime.now(UTC)
    event.locked_by = None
    event.locked_until = None
    event.lease_token = None
    event.last_error = None
    db.commit()
    return True


def retry_outbox_event(
    db: Session,
    *,
    event_id: UUID,
    lease_token: UUID,
    error: str,
    retry_delay_seconds: int = 30,
    max_attempts: int = 8,
) -> bool:
    if not 1 <= retry_delay_seconds <= 86_400 or not 1 <= max_attempts <= 100:
        raise ValueError("Invalid outbox retry policy")
    event = db.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update())
    if event is None or event.status != "processing" or event.lease_token != lease_token:
        return False
    event.status = "dead_letter" if event.attempts >= max_attempts else "pending"
    event.available_at = datetime.now(UTC) + timedelta(seconds=retry_delay_seconds)
    event.locked_by = None
    event.locked_until = None
    event.lease_token = None
    event.last_error = error.strip()[:1000] if error.strip() else "Delivery failed"
    db.commit()
    return True
