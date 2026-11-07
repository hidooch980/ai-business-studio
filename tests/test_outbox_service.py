from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.identity.models import Tenant
from backend.app.outbox.models import OutboxEvent
from backend.app.outbox.service import (
    claim_outbox_events,
    enqueue_outbox_event,
    mark_outbox_delivered,
    retry_outbox_event,
)


def test_outbox_enqueue_claim_retry_and_acknowledge_with_lease_token() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as db:
            tenant = Tenant(name="Outbox tenant", slug="outbox-tenant")
            db.add(tenant)
            db.flush()
            event = enqueue_outbox_event(
                db,
                tenant_id=tenant.id,
                event_type="inventory.movement.created",
                aggregate_type="inventory_movement",
                aggregate_id="movement-1",
                dedupe_key="movement:1",
                payload={"quantity_delta": 4},
            )
            event_id = event.id
            db.commit()

            duplicate = enqueue_outbox_event(
                db,
                tenant_id=tenant.id,
                event_type="inventory.movement.created",
                aggregate_type="inventory_movement",
                aggregate_id="movement-1",
                dedupe_key="movement:1",
                payload={"quantity_delta": 4},
            )
            assert duplicate.id == event_id
            db.commit()

            first_claim = claim_outbox_events(db, worker_id="worker-a", limit=10, lease_seconds=5)
            assert len(first_claim) == 1
            first_token = first_claim[0].lease_token
            assert first_token is not None
            assert first_claim[0].attempts == 1

            with Session(engine, expire_on_commit=False) as other:
                assert not mark_outbox_delivered(other, event_id=event_id, lease_token=uuid4())

            first_claim[0].locked_until = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
            second_claim = claim_outbox_events(db, worker_id="worker-b", limit=10, lease_seconds=5)
            assert len(second_claim) == 1
            second_token = second_claim[0].lease_token
            assert second_token is not None
            assert second_claim[0].attempts == 2

            assert not mark_outbox_delivered(db, event_id=event_id, lease_token=first_token)
            assert mark_outbox_delivered(db, event_id=event_id, lease_token=second_token)
            delivered = db.get(OutboxEvent, event_id)
            assert delivered is not None
            assert delivered.status == "delivered"
            assert delivered.delivered_at is not None
            assert delivered.lease_token is None
    finally:
        engine.dispose()


def test_outbox_moves_to_dead_letter_after_retry_limit() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as db:
            tenant = Tenant(name="Dead letter tenant", slug="dead-letter-tenant")
            db.add(tenant)
            db.flush()
            event = enqueue_outbox_event(
                db,
                tenant_id=tenant.id,
                event_type="test.event",
                aggregate_type="test",
                aggregate_id="test-1",
                dedupe_key="test:1",
                payload={"value": 1},
            )
            event_id = event.id
            db.commit()
            claimed = claim_outbox_events(db, worker_id="worker", limit=1)
            assert len(claimed) == 1
            assert retry_outbox_event(
                db,
                event_id=event_id,
                lease_token=claimed[0].lease_token,
                error="provider unavailable",
                retry_delay_seconds=1,
                max_attempts=1,
            )
            failed = db.get(OutboxEvent, event_id)
            assert failed is not None
            assert failed.status == "dead_letter"
            assert failed.last_error == "provider unavailable"
    finally:
        engine.dispose()
