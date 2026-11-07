from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.identity.models import Tenant
from backend.app.outbox.models import OutboxEvent
from backend.app.outbox.service import enqueue_outbox_event
from backend.app.outbox.worker import OutboxMessage, run_outbox_batch


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_worker_delivers_registered_handler_and_acknowledges(tmp_path):
    engine, factory = _factory(tmp_path)
    seen = []

    try:
        with factory.begin() as db:
            tenant = Tenant(name="Worker tenant", slug="worker-tenant")
            db.add(tenant)
            db.flush()
            event = enqueue_outbox_event(
                db,
                tenant_id=tenant.id,
                event_type="sample.created",
                aggregate_type="sample",
                aggregate_id="sample-1",
                dedupe_key="sample:1",
                payload={"value": 7},
            )
            event_id = event.id

        def handler(db: Session, message: OutboxMessage) -> None:
            seen.append((message.event_type, message.payload["value"]))

        result = run_outbox_batch(factory, worker_id="worker-a", handlers={"sample.created": handler})
        assert result == {"claimed": 1, "delivered": 1, "retried": 0, "dead_letter": 0}
        assert seen == [("sample.created", 7)]
        with factory() as db:
            stored = db.get(OutboxEvent, event_id)
            assert stored is not None
            assert stored.status == "delivered"
    finally:
        engine.dispose()


def test_worker_retries_handler_failure(tmp_path):
    engine, factory = _factory(tmp_path)
    try:
        with factory.begin() as db:
            tenant = Tenant(name="Retry tenant", slug="retry-tenant")
            db.add(tenant)
            db.flush()
            event = enqueue_outbox_event(
                db,
                tenant_id=tenant.id,
                event_type="sample.failed",
                aggregate_type="sample",
                aggregate_id="sample-2",
                dedupe_key="sample:2",
                payload={"value": 9},
            )
            event_id = event.id

        def handler(_db: Session, _message: OutboxMessage) -> None:
            raise RuntimeError("temporary failure")

        result = run_outbox_batch(
            factory,
            worker_id="worker-b",
            handlers={"sample.failed": handler},
            retry_delay_seconds=30,
            max_attempts=3,
        )
        assert result == {"claimed": 1, "delivered": 0, "retried": 1, "dead_letter": 0}
        with factory() as db:
            stored = db.get(OutboxEvent, event_id)
            assert stored is not None
            assert stored.status == "pending"
            assert stored.attempts == 1
            assert "temporary failure" in (stored.last_error or "")
    finally:
        engine.dispose()


def test_worker_dead_letters_unhandled_event(tmp_path):
    engine, factory = _factory(tmp_path)
    try:
        with factory.begin() as db:
            tenant = Tenant(name="Unknown tenant", slug="unknown-tenant")
            db.add(tenant)
            db.flush()
            event = enqueue_outbox_event(
                db,
                tenant_id=tenant.id,
                event_type="unknown.event",
                aggregate_type="unknown",
                aggregate_id="unknown-1",
                dedupe_key="unknown:1",
                payload={},
            )
            event_id = event.id

        result = run_outbox_batch(
            factory,
            worker_id="worker-c",
            handlers={},
            max_attempts=1,
        )
        assert result == {"claimed": 1, "delivered": 0, "retried": 0, "dead_letter": 1}
        with factory() as db:
            stored = db.get(OutboxEvent, event_id)
            assert stored is not None
            assert stored.status == "dead_letter"
    finally:
        engine.dispose()
