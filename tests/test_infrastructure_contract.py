from retail_app.infrastructure.idempotency import request_digest
from retail_app.infrastructure.audit import record_audit
from retail_app.infrastructure.events import append_domain_event


def test_idempotency_digest_is_canonical_across_mapping_order():
    assert request_digest({"b": 2, "a": 1}) == request_digest({"a": 1, "b": 2})


def test_idempotency_digest_rejects_non_json_numbers():
    import pytest
    with pytest.raises(ValueError):
        request_digest({"amount": float("nan")})


class RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))


def test_audit_writer_uses_callers_transaction_and_validates_outcome():
    import pytest
    connection = RecordingConnection()
    event_id = record_audit(
        connection, tenant_id="tenant", actor_identity_id=None,
        action="supplier.create", resource_type="supplier",
        resource_id="supplier-1", outcome="success",
    )
    assert event_id
    assert len(connection.calls) == 1
    with pytest.raises(ValueError):
        record_audit(
            connection, tenant_id="tenant", actor_identity_id=None,
            action="x", resource_type="supplier", resource_id=None,
            outcome="unknown",
        )


def test_domain_event_and_outbox_are_written_together_on_same_connection():
    connection = RecordingConnection()
    event_id, outbox_id = append_domain_event(
        connection, tenant_id="tenant", aggregate_type="purchase_order",
        aggregate_id="po-1", aggregate_version=1, event_type="purchase_order.created",
        payload={"status": "draft"}, destination="internal",
    )
    assert event_id and outbox_id
    assert len(connection.calls) == 2
