from contextlib import contextmanager
from datetime import date

import pytest

from retail_app.procurement.purchase_orders import PurchaseOrder, PurchaseOrderLine
from retail_app.procurement.service import create_purchase_order, create_supplier
from retail_app.procurement.suppliers import Supplier
from retail_app.security.authorization import AccessContext, AccessDenied, Role


class Result:
    def __init__(self, row=None, rowcount=1):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "INSERT INTO idempotency_records" in query:
            return Result(("reserved",))
        if "SELECT status FROM suppliers" in query:
            return Result(("active",))
        return Result(rowcount=1)


class FakeDatabase:
    def __init__(self):
        self.connection = RecordingConnection()
        self.entered = False

    @contextmanager
    def tenant_transaction(self, *, tenant_id, subject_id=None):
        self.entered = True
        self.context = (tenant_id, subject_id)
        yield self.connection


TENANT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OWNER = "aaaaaaaa-1001-4000-8000-000000000001"
BRANCH = "aaaaaaaa-0001-4000-8000-000000000001"
SUPPLIER = "aaaaaaaa-4001-4000-8000-000000000001"
ORDER = "aaaaaaaa-5001-4000-8000-000000000001"
ITEM = "aaaaaaaa-6001-4000-8000-000000000001"


def test_create_supplier_writes_supplier_audit_event_outbox_and_idempotency():
    database = FakeDatabase()
    actor = AccessContext(OWNER, TENANT, Role.OWNER_ADMIN)
    supplier = Supplier(SUPPLIER, TENANT, "Example Supplies")

    result = create_supplier(
        database, actor, supplier, idempotency_key="supplier-create-0001"
    )

    assert result["id"] == SUPPLIER
    assert database.entered
    sql = [query for query, _ in database.connection.calls]
    assert any("INSERT INTO suppliers" in query for query in sql)
    assert any("INSERT INTO audit_events" in query for query in sql)
    assert any("INSERT INTO domain_events" in query for query in sql)
    assert any("INSERT INTO outbox_messages" in query for query in sql)
    assert any("UPDATE idempotency_records" in query for query in sql)


def test_branch_manager_cannot_create_tenant_wide_supplier():
    database = FakeDatabase()
    actor = AccessContext("manager", TENANT, Role.BRANCH_MANAGER, frozenset({BRANCH}))
    supplier = Supplier(SUPPLIER, TENANT, "Example Supplies")

    with pytest.raises(AccessDenied):
        create_supplier(database, actor, supplier, idempotency_key="supplier-create-0002")
    assert not database.entered


def test_create_purchase_order_checks_supplier_and_writes_atomic_records():
    database = FakeDatabase()
    actor = AccessContext("manager", TENANT, Role.BRANCH_MANAGER, frozenset({BRANCH}))
    order = PurchaseOrder(
        id=ORDER,
        tenant_id=TENANT,
        branch_id=BRANCH,
        supplier_id=SUPPLIER,
        currency="EUR",
        order_date=date(2026, 11, 8),
        lines=(PurchaseOrderLine(1, ITEM, "Equipment", 2000, 125),),
        order_number="PO-2026-001",
    )

    result = create_purchase_order(
        database, actor, order, idempotency_key="purchase-order-create-01"
    )

    assert result["status"] == "draft"
    assert result["total_minor"] == 250
    sql = [query for query, _ in database.connection.calls]
    assert any("SELECT status FROM suppliers" in query for query in sql)
    assert any("INSERT INTO purchase_orders" in query for query in sql)
    assert any("INSERT INTO purchase_order_lines" in query for query in sql)
    assert any("INSERT INTO audit_events" in query for query in sql)
    assert any("INSERT INTO domain_events" in query for query in sql)
    assert any("INSERT INTO outbox_messages" in query for query in sql)


def test_purchase_order_cannot_cross_tenant_boundary():
    database = FakeDatabase()
    actor = AccessContext(OWNER, TENANT, Role.OWNER_ADMIN)
    order = PurchaseOrder(
        id=ORDER,
        tenant_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        branch_id=BRANCH,
        supplier_id=SUPPLIER,
        currency="EUR",
        order_date=date(2026, 11, 8),
        lines=(PurchaseOrderLine(1, ITEM, "Equipment", 1000, 100),),
        order_number="PO-2026-002",
    )

    with pytest.raises(PermissionError):
        create_purchase_order(
            database, actor, order, idempotency_key="purchase-order-create-02"
        )
    assert not database.entered
