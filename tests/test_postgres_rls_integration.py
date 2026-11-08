from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = [
    ROOT / "migrations" / "0001_identity_security.sql",
    ROOT / "migrations" / "0002_transactional_infrastructure.sql",
    ROOT / "migrations" / "0003_suppliers_purchase_orders.sql",
    ROOT / "migrations" / "0004_receipts_invoices_payments.sql",
]
RUNTIME_URL = "postgresql://retail_runtime:runtime-test-only@localhost:5432/retail_test"

TENANT_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
TENANT_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
BRANCH_A = UUID("aaaaaaaa-0001-4000-8000-000000000001")
BRANCH_B = UUID("bbbbbbbb-0001-4000-8000-000000000001")
USER_A = UUID("aaaaaaaa-1001-4000-8000-000000000001")
USER_A2 = UUID("aaaaaaaa-1002-4000-8000-000000000002")
USER_B = UUID("bbbbbbbb-1001-4000-8000-000000000001")
SESSION_A = UUID("aaaaaaaa-2001-4000-8000-000000000001")
SESSION_A2 = UUID("aaaaaaaa-2002-4000-8000-000000000002")
SESSION_B = UUID("bbbbbbbb-2001-4000-8000-000000000001")
OTP_ANON = UUID("cccccccc-3001-4000-8000-000000000001")


@pytest.fixture(scope="session", autouse=True)
def postgres_schema():
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "CREATE ROLE auth_bootstrap_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        conn.execute(
            "CREATE ROLE retail_runtime LOGIN PASSWORD 'runtime-test-only' "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        from retail_app.infrastructure.migrations import apply_migrations

        assert apply_migrations(DATABASE_URL, ROOT / "migrations") == [
            "0001_identity_security.sql",
            "0002_transactional_infrastructure.sql",
            "0003_suppliers_purchase_orders.sql",
            "0004_receipts_invoices_payments.sql",
            "0005_session_bootstrap_rls.sql",
        ]
        conn.execute("GRANT USAGE ON SCHEMA public TO retail_runtime")
        conn.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO retail_runtime"
        )
        conn.execute("REVOKE ALL ON auth_session_bootstrap FROM retail_runtime")
        conn.execute(
            """
            INSERT INTO tenants (id, name) VALUES (%s, 'Tenant A'), (%s, 'Tenant B');
            """,
            (TENANT_A, TENANT_B),
        )
        conn.execute(
            """
            INSERT INTO branches (id, tenant_id, name) VALUES
                (%s, %s, 'A Main'), (%s, %s, 'B Main');
            """,
            (BRANCH_A, TENANT_A, BRANCH_B, TENANT_B),
        )
        conn.execute(
            """
            INSERT INTO identities (id, account_type, phone_e164) VALUES
                (%s, 'workforce', '+12025550101'),
                (%s, 'customer', '+12025550102'),
                (%s, 'workforce', '+12025550103');
            """,
            (USER_A, USER_A2, USER_B),
        )
        conn.execute(
            """
            INSERT INTO tenant_memberships (tenant_id, identity_id, role) VALUES
                (%s, %s, 'owner_admin'), (%s, %s, 'customer'), (%s, %s, 'owner_admin');
            """,
            (TENANT_A, USER_A, TENANT_A, USER_A2, TENANT_B, USER_B),
        )
        conn.execute(
            """
            INSERT INTO branch_memberships (tenant_id, branch_id, identity_id) VALUES
                (%s, %s, %s), (%s, %s, %s);
            """,
            (TENANT_A, BRANCH_A, USER_A, TENANT_B, BRANCH_B, USER_B),
        )
        conn.execute(
            """
            INSERT INTO auth_sessions
                (id, tenant_id, identity_id, refresh_token_hash, expires_at)
            VALUES
                (%s, %s, %s, decode(repeat('01', 32), 'hex'), now() + interval '1 day'),
                (%s, %s, %s, decode(repeat('02', 32), 'hex'), now() + interval '1 day'),
                (%s, %s, %s, decode(repeat('03', 32), 'hex'), now() + interval '1 day');
            """,
            (
                SESSION_A, TENANT_A, USER_A,
                SESSION_A2, TENANT_A, USER_A2,
                SESSION_B, TENANT_B, USER_B,
            ),
        )
        conn.execute(
            """
            INSERT INTO otp_challenges
                (id, identifier_fingerprint, code_hmac, purpose, channel, expires_at, resend_after)
            VALUES (%s, decode(repeat('aa', 32), 'hex'), decode(repeat('bb', 32), 'hex'),
                    'login', 'sms', now() + interval '5 minutes', now() + interval '1 minute');
            """,
            (OTP_ANON,),
        )
    yield
    # CI uses an ephemeral database; the service is discarded after the job.


@pytest.fixture
def runtime():
    with psycopg.connect(RUNTIME_URL) as conn:
        yield conn


def set_context(conn, tenant: UUID | None = None, subject: UUID | None = None, onboarding=False):
    conn.execute(
        "SELECT set_config('app.tenant_id', %s, true)",
        (str(tenant) if tenant else "",),
    )
    conn.execute(
        "SELECT set_config('app.subject_id', %s, true)",
        (str(subject) if subject else "",),
    )
    conn.execute(
        "SELECT set_config('app.otp_onboarding', %s, true)",
        ("true" if onboarding else "false",),
    )


def test_1_migration_applies_and_forces_rls_on_all_scoped_tables():
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """
            SELECT c.relname, c.relforcerowsecurity
            FROM pg_class c
            WHERE c.relname IN (
                'tenants', 'branches', 'identities', 'tenant_memberships',
                'branch_memberships', 'auth_sessions', 'otp_challenges',
                'security_audit_events', 'idempotency_records', 'domain_events',
                'outbox_messages', 'audit_events', 'suppliers', 'purchase_orders',
                'purchase_order_lines', 'goods_receipts', 'goods_receipt_lines',
                'inventory_movements', 'supplier_invoices', 'supplier_invoice_lines', 'accounts_payable',
                'supplier_payments', 'payment_allocations', 'financial_ledger_entries'
            )
            """
        ).fetchall()
    assert len(rows) == 24
    assert all(forced for _, forced in rows)


def test_2_missing_request_context_sees_no_tenant_data_and_cannot_insert(runtime):
    with runtime.transaction():
        set_context(runtime)
        assert runtime.execute("SELECT count(*) FROM tenants").fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege), runtime.transaction():
            runtime.execute(
                "INSERT INTO tenants (id, name) VALUES (%s, 'forbidden')",
                (UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),),
            )


def test_3_tenant_context_cannot_read_another_tenant(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        assert runtime.execute("SELECT id FROM tenants").fetchall() == [(TENANT_A,)]
        assert runtime.execute("SELECT id FROM branches").fetchall() == [(BRANCH_A,)]


def test_4_branch_membership_rows_are_tenant_scoped(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        rows = runtime.execute(
            "SELECT branch_id, identity_id FROM branch_memberships"
        ).fetchall()
        assert rows == [(BRANCH_A, USER_A)]


def test_5_sessions_are_private_to_the_authenticated_subject(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        rows = runtime.execute("SELECT id FROM auth_sessions").fetchall()
        assert rows == [(SESSION_A,)]


def test_6_identity_visibility_is_self_or_same_tenant_only(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        visible = {
            row[0] for row in runtime.execute("SELECT id FROM identities").fetchall()
        }
        assert visible == {USER_A, USER_A2,}
        with pytest.raises(psycopg.errors.InsufficientPrivilege), runtime.transaction():
            runtime.execute(
                """
                INSERT INTO identities (id, account_type, phone_e164)
                VALUES (%s, 'workforce', '+12025550999')
                """,
                (UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),),
            )


def test_7_anonymous_otp_rows_require_explicit_onboarding_context(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A, onboarding=False)
        assert runtime.execute(
            "SELECT count(*) FROM otp_challenges WHERE tenant_id IS NULL"
        ).fetchone()[0] == 0
    with runtime.transaction():
        set_context(runtime, onboarding=True)
        assert runtime.execute(
            "SELECT id FROM otp_challenges WHERE tenant_id IS NULL"
        ).fetchall() == [(OTP_ANON,)]
        runtime.execute(
            """
            INSERT INTO otp_challenges
                (id, identifier_fingerprint, code_hmac, purpose, channel, expires_at, resend_after)
            VALUES (%s, decode(repeat('cc', 32), 'hex'), decode(repeat('dd', 32), 'hex'),
                    'login', 'sms', now() + interval '5 minutes', now() + interval '1 minute')
            """,
            (UUID("cccccccc-3002-4000-8000-000000000002"),),
        )



def test_8_procurement_tables_are_tenant_isolated(runtime):
    supplier_id = UUID("aaaaaaaa-4001-4000-8000-000000000001")
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        runtime.execute(
            """
            INSERT INTO suppliers (tenant_id, id, legal_name)
            VALUES (%s, %s, 'Tenant A Supplier')
            """,
            (TENANT_A, supplier_id),
        )
        assert runtime.execute(
            "SELECT legal_name FROM suppliers WHERE id = %s", (supplier_id,)
        ).fetchone() == ("Tenant A Supplier",)
        set_context(runtime, TENANT_B, USER_B)
        assert runtime.execute(
            "SELECT id FROM suppliers WHERE id = %s", (supplier_id,)
        ).fetchall() == []


def test_9_idempotency_and_event_records_are_tenant_scoped(runtime):
    from uuid import uuid4

    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        record_id = uuid4()
        runtime.execute(
            """
            INSERT INTO idempotency_records
                (id, tenant_id, operation, idempotency_key, request_sha256, state)
            VALUES (%s, %s, 'purchase_order.create', 'test-key-0000001',
                    decode(repeat('01', 32), 'hex'), 'processing')
            """,
            (record_id, TENANT_A),
        )
        event_id = uuid4()
        runtime.execute(
            """
            INSERT INTO domain_events
                (id, tenant_id, aggregate_type, aggregate_id, aggregate_version,
                 event_type, payload)
            VALUES (%s, %s, 'purchase_order', %s, 1,
                    'purchase_order.created', '{"status":"draft"}'::jsonb)
            """,
            (event_id, TENANT_A, uuid4()),
        )
        runtime.execute(
            """
            INSERT INTO outbox_messages (id, tenant_id, event_id, destination)
            VALUES (%s, %s, %s, 'internal')
            """,
            (uuid4(), TENANT_A, event_id),
        )
        assert runtime.execute("SELECT count(*) FROM idempotency_records").fetchone()[0] == 1
        set_context(runtime, TENANT_B, USER_B)
        assert runtime.execute("SELECT count(*) FROM idempotency_records").fetchone()[0] == 0
        assert runtime.execute("SELECT count(*) FROM domain_events").fetchone()[0] == 0
        assert runtime.execute("SELECT count(*) FROM outbox_messages").fetchone()[0] == 0


def test_10_domain_events_and_business_audit_are_append_only(runtime):
    from uuid import uuid4

    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        event_id = uuid4()
        runtime.execute(
            """
            INSERT INTO domain_events
                (id, tenant_id, aggregate_type, aggregate_id, aggregate_version,
                 event_type, payload)
            VALUES (%s, %s, 'supplier', %s, 1, 'supplier.created', '{}'::jsonb)
            """,
            (event_id, TENANT_A, uuid4()),
        )
        with pytest.raises(psycopg.errors.RaiseException), runtime.transaction():
            runtime.execute(
                "UPDATE domain_events SET event_type = 'supplier.changed' WHERE id = %s",
                (event_id,),
            )


def test_11_supplier_and_purchase_order_services_commit_atomically_and_replay(runtime):
    from datetime import date
    from uuid import uuid4

    from retail_app.infrastructure.database import PostgresDatabase
    from retail_app.infrastructure.idempotency import IdempotencyConflict
    from retail_app.procurement.purchase_orders import PurchaseOrder, PurchaseOrderLine
    from retail_app.procurement.service import create_purchase_order, create_supplier
    from retail_app.procurement.suppliers import Supplier
    from retail_app.security.authorization import AccessContext, Role

    database = PostgresDatabase(RUNTIME_URL)
    actor = AccessContext(str(USER_A), str(TENANT_A), Role.OWNER_ADMIN)
    supplier_id = str(uuid4())
    supplier = Supplier(supplier_id, str(TENANT_A), "Integration Supplier")

    created_supplier = create_supplier(
        database, actor, supplier, idempotency_key="supplier-integration-0001"
    )
    replayed_supplier = create_supplier(
        database, actor, supplier, idempotency_key="supplier-integration-0001"
    )
    assert replayed_supplier == created_supplier

    with pytest.raises(IdempotencyConflict):
        create_supplier(
            database, actor,
            Supplier(supplier_id, str(TENANT_A), "Changed Supplier Name"),
            idempotency_key="supplier-integration-0001",
        )

    order = PurchaseOrder(
        id=str(uuid4()),
        tenant_id=str(TENANT_A),
        branch_id=str(BRANCH_A),
        supplier_id=supplier_id,
        currency="EUR",
        order_date=date(2026, 11, 8),
        lines=(PurchaseOrderLine(1, str(uuid4()), "Test item", 2000, 125),),
        order_number="PO-INTEGRATION-0001",
    )
    created_order = create_purchase_order(
        database, actor, order, idempotency_key="purchase-order-integration-01"
    )
    replayed_order = create_purchase_order(
        database, actor, order, idempotency_key="purchase-order-integration-01"
    )
    assert replayed_order == created_order
    assert created_order["total_minor"] == 250

    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        assert runtime.execute(
            "SELECT count(*) FROM suppliers WHERE id = %s", (supplier_id,)
        ).fetchone()[0] == 1
        assert runtime.execute(
            "SELECT count(*) FROM purchase_order_lines WHERE purchase_order_id = %s",
            (order.id,),
        ).fetchone()[0] == 1
        assert runtime.execute(
            "SELECT count(*) FROM audit_events WHERE resource_id IN (%s, %s)",
            (supplier_id, order.id),
        ).fetchone()[0] == 2


def test_12_concurrent_supplier_create_replays_one_idempotent_result():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4

    from retail_app.infrastructure.database import PostgresDatabase
    from retail_app.procurement.service import create_supplier
    from retail_app.procurement.suppliers import Supplier
    from retail_app.security.authorization import AccessContext, Role

    database = PostgresDatabase(RUNTIME_URL)
    actor = AccessContext(str(USER_A), str(TENANT_A), Role.OWNER_ADMIN)
    supplier = Supplier(str(uuid4()), str(TENANT_A), "Concurrent Supplier")
    barrier = Barrier(2)

    def create_once():
        barrier.wait(timeout=10)
        return create_supplier(
            database, actor, supplier, idempotency_key="supplier-concurrent-0001"
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_once(), range(2)))

    assert results[0] == results[1]



def test_13_full_procurement_to_payment_lifecycle(runtime):
    from datetime import UTC, date, datetime
    from uuid import uuid4

    from retail_app.infrastructure.database import PostgresDatabase
    from retail_app.procurement.chain import (
        approve_purchase_order,
        get_purchase_order,
        get_stock_balance,
        list_accounts_payable,
        match_supplier_invoice,
        receive_goods,
        record_supplier_payment,
        update_draft_purchase_order,
    )
    from retail_app.procurement.purchase_orders import PurchaseOrder, PurchaseOrderLine
    from retail_app.procurement.service import create_purchase_order, create_supplier
    from retail_app.procurement.suppliers import Supplier
    from retail_app.security.authorization import AccessContext, Role

    database = PostgresDatabase(RUNTIME_URL)
    actor = AccessContext(str(USER_A), str(TENANT_A), Role.OWNER_ADMIN)
    supplier_id, order_id, invoice_id = str(uuid4()), str(uuid4()), str(uuid4())
    item_id = str(uuid4())
    supplier = Supplier(supplier_id, str(TENANT_A), "Lifecycle Supplier")
    create_supplier(database, actor, supplier, idempotency_key="lifecycle-supplier-0001")

    order = PurchaseOrder(
        id=order_id, tenant_id=str(TENANT_A), branch_id=str(BRANCH_A),
        supplier_id=supplier_id, currency="EUR", order_date=date(2026, 11, 8),
        lines=(PurchaseOrderLine(1, item_id, "Lifecycle stock", 3000, 1000),),
        order_number="PO-LIFECYCLE-0001",
    )
    create_purchase_order(database, actor, order, idempotency_key="lifecycle-po-create-0001")
    update_draft_purchase_order(
        database, actor, order_id, supplier_id=supplier_id, currency="EUR",
        order_date=date(2026, 11, 8),
        lines=[{
            "line_number": 1, "item_id": item_id,
            "description": "Lifecycle stock edited", "quantity_milli": 3000,
            "unit_price_minor": 1000,
        }],
        idempotency_key="lifecycle-po-update-0001",
    )
    assert get_purchase_order(database, actor, order_id)["lines"][0]["description"] == "Lifecycle stock edited"
    approve_purchase_order(
        database, actor, order_id, idempotency_key="lifecycle-po-approve-0001"
    )

    receipt_one = receive_goods(
        database, actor, order_id, receipt_number="GR-LIFECYCLE-0001",
        received_at=datetime(2026, 11, 8, tzinfo=UTC),
        lines=[{
            "po_line_number": 1, "received_quantity_milli": 1000,
            "accepted_quantity_milli": 1000, "rejected_quantity_milli": 0,
        }],
        idempotency_key="lifecycle-receipt-0001",
    )
    assert receipt_one["purchase_order_status"] == "partially_received"
    receipt_two = receive_goods(
        database, actor, order_id, receipt_number="GR-LIFECYCLE-0002",
        received_at=datetime(2026, 11, 9, tzinfo=UTC),
        lines=[{
            "po_line_number": 1, "received_quantity_milli": 2000,
            "accepted_quantity_milli": 2000, "rejected_quantity_milli": 0,
        }],
        idempotency_key="lifecycle-receipt-0002",
    )
    assert receipt_two["purchase_order_status"] == "received"
    assert get_stock_balance(database, actor, branch_id=str(BRANCH_A), item_id=item_id)["on_hand_quantity_milli"] == 3000
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        receipt_line_ids = [
            str(row[0]) for row in runtime.execute(
                """SELECT grl.id FROM goods_receipt_lines grl
                   JOIN goods_receipts gr
                     ON gr.tenant_id = grl.tenant_id AND gr.id = grl.goods_receipt_id
                   WHERE grl.goods_receipt_id IN (%s, %s) ORDER BY gr.received_at""",
                (receipt_one["id"], receipt_two["id"]),
            ).fetchall()
        ]
    assert len(receipt_line_ids) == 2

    matched = match_supplier_invoice(
        database, actor, invoice_id=invoice_id, supplier_id=supplier_id,
        purchase_order_id=order_id, invoice_number="INV-LIFECYCLE-0001",
        currency="EUR", invoice_date=date(2026, 11, 8), due_date=date(2026, 11, 20),
        invoice_total_minor=3000,
        lines=[
            {
                "po_line_number": 1, "goods_receipt_line_id": receipt_line_ids[0],
                "quantity_milli": 1000, "unit_price_minor": 1000,
            },
            {
                "po_line_number": 1, "goods_receipt_line_id": receipt_line_ids[1],
                "quantity_milli": 2000, "unit_price_minor": 1000,
            },
        ],
        idempotency_key="lifecycle-invoice-match-0001",
    )
    assert matched["status"] == "matched"
    assert matched["payable_id"]

    disputed = match_supplier_invoice(
        database, actor, invoice_id=str(uuid4()), supplier_id=supplier_id,
        purchase_order_id=order_id, invoice_number="INV-LIFECYCLE-DISPUTED",
        currency="EUR", invoice_date=date(2026, 11, 8), due_date=date(2026, 11, 20),
        invoice_total_minor=2000,
        lines=[{
            "po_line_number": 1, "goods_receipt_line_id": receipt_line_ids[0],
            "quantity_milli": 1000, "unit_price_minor": 2000,
        }],
        idempotency_key="lifecycle-invoice-disputed-0001",
    )
    assert disputed["status"] == "disputed"
    assert disputed["payable_id"] is None
    assert disputed["mismatches"]

    outstanding = list_accounts_payable(database, actor)
    assert len(outstanding) == 1
    assert outstanding[0]["outstanding_amount_minor"] == 3000

    payment_id = str(uuid4())
    payment_args = {
        "payment_id": payment_id, "supplier_id": supplier_id,
        "payment_reference": "PAY-LIFECYCLE-0001", "currency": "EUR",
        "amount_minor": 1000, "paid_at": datetime(2026, 11, 8, tzinfo=UTC),
        "method": "bank_transfer",
        "allocations": [{"payable_id": matched["payable_id"], "amount_minor": 1000}],
        "idempotency_key": "lifecycle-payment-0001",
    }
    payment = record_supplier_payment(database, actor, **payment_args)
    replayed_payment = record_supplier_payment(database, actor, **payment_args)
    assert replayed_payment == payment
    assert payment["status"] == "posted"
    assert payment["allocated_minor"] == 1000
    assert list_accounts_payable(database, actor)[0]["status"] == "partially_paid"
    assert list_accounts_payable(database, actor)[0]["outstanding_amount_minor"] == 2000

    with pytest.raises(psycopg.errors.UniqueViolation):
        record_supplier_payment(
            database, actor, payment_id=str(uuid4()), supplier_id=supplier_id,
            payment_reference="PAY-LIFECYCLE-0001", currency="EUR", amount_minor=1000,
            paid_at=datetime(2026, 11, 8, tzinfo=UTC), method="bank_transfer",
            allocations=[{"payable_id": matched["payable_id"], "amount_minor": 1000}],
            idempotency_key="lifecycle-payment-duplicate-key",
        )

    final_payment = record_supplier_payment(
        database, actor, payment_id=str(uuid4()), supplier_id=supplier_id,
        payment_reference="PAY-LIFECYCLE-0002", currency="EUR", amount_minor=2000,
        paid_at=datetime(2026, 11, 9, tzinfo=UTC), method="bank_transfer",
        allocations=[{"payable_id": matched["payable_id"], "amount_minor": 2000}],
        idempotency_key="lifecycle-payment-0002",
    )
    assert final_payment["status"] == "posted"
    assert final_payment["allocated_minor"] == 2000
    assert list_accounts_payable(database, actor)[0]["status"] == "paid"
    assert list_accounts_payable(database, actor)[0]["outstanding_amount_minor"] == 0

    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        journal_rows = runtime.execute(
            """SELECT source_type, SUM(debit_minor), SUM(credit_minor)
               FROM financial_ledger_entries
               WHERE source_id IN (%s, %s, %s, %s, %s) GROUP BY source_type""",
            (receipt_one["id"], receipt_two["id"], invoice_id, payment["id"], final_payment["id"]),
        ).fetchall()
        assert len(journal_rows) == 3
        assert all(debit == credit for _, debit, credit in journal_rows)
        assert runtime.execute(
            "SELECT count(*) FROM payment_allocations WHERE payable_id = %s",
            (matched["payable_id"],),
        ).fetchone()[0] == 2



def test_14_overdelivery_requires_explicit_flag_and_discrepancy_code(runtime):
    from datetime import UTC, date, datetime
    from uuid import uuid4

    from retail_app.infrastructure.database import PostgresDatabase
    from retail_app.procurement.chain import approve_purchase_order, get_stock_balance, receive_goods
    from retail_app.procurement.purchase_orders import PurchaseOrder, PurchaseOrderLine
    from retail_app.procurement.service import create_purchase_order, create_supplier
    from retail_app.procurement.suppliers import Supplier
    from retail_app.security.authorization import AccessContext, Role

    database = PostgresDatabase(RUNTIME_URL)
    actor = AccessContext(str(USER_A), str(TENANT_A), Role.OWNER_ADMIN)
    supplier_id, order_id = str(uuid4()), str(uuid4())
    create_supplier(
        database, actor, Supplier(supplier_id, str(TENANT_A), "Overdelivery Supplier"),
        idempotency_key="overdelivery-supplier-0001",
    )
    order = PurchaseOrder(
        id=order_id, tenant_id=str(TENANT_A), branch_id=str(BRANCH_A),
        supplier_id=supplier_id, currency="EUR", order_date=date(2026, 11, 8),
        lines=(PurchaseOrderLine(1, str(uuid4()), "Overdelivery test", 1000, 1000),),
        order_number="PO-OVERDELIVERY-0001",
    )
    create_purchase_order(database, actor, order, idempotency_key="overdelivery-po-0001")
    approve_purchase_order(database, actor, order_id, idempotency_key="overdelivery-approve-0001")
    receipt_input = {
        "receipt_number": "GR-OVERDELIVERY-0001",
        "received_at": datetime(2026, 11, 8, tzinfo=UTC),
        "lines": [{
            "po_line_number": 1, "received_quantity_milli": 2000,
            "accepted_quantity_milli": 1000, "rejected_quantity_milli": 1000,
            "discrepancy_code": "overdelivery",
        }],
        "idempotency_key": "overdelivery-receipt-0001",
    }
    manager = AccessContext(
        str(USER_A), str(TENANT_A), Role.BRANCH_MANAGER, frozenset({str(BRANCH_A)})
    )
    # Keep the database-backed role aligned with the manager context so the
    # transaction boundary does not reject the call before the business rule.
    with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
        admin.execute(
            "UPDATE tenant_memberships SET role = 'branch_manager' "
            "WHERE tenant_id = %s AND identity_id = %s",
            (TENANT_A, USER_A),
        )
    try:
        with pytest.raises(PermissionError, match="owner/admin"):
            receive_goods(database, manager, order_id, **receipt_input, allow_overdelivery=True)
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(
                "UPDATE tenant_memberships SET role = 'owner_admin' "
                "WHERE tenant_id = %s AND identity_id = %s",
                (TENANT_A, USER_A),
            )
    with pytest.raises(ValueError, match="explicit approval"):
        receive_goods(database, actor, order_id, **receipt_input)
    receipt = receive_goods(database, actor, order_id, **receipt_input, allow_overdelivery=True)
    assert receipt["purchase_order_status"] == "received"
    assert receipt["discrepancies"][0]["code"] == "overdelivery"
    assert get_stock_balance(database, actor, branch_id=str(BRANCH_A), item_id=order.lines[0].item_id)["on_hand_quantity_milli"] == 1000



def test_15_database_rejects_unbalanced_financial_journals(runtime):
    from uuid import uuid4

    with pytest.raises(psycopg.errors.RaiseException, match="not balanced"), runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        runtime.execute(
                """INSERT INTO financial_ledger_entries
                   (tenant_id, id, journal_id, source_type, source_id, account_code,
                    currency, debit_minor, credit_minor)
                   VALUES (%s, %s, %s, 'test', %s, 'INVENTORY', 'EUR', 100, 0)""",
                (TENANT_A, uuid4(), uuid4(), uuid4()),
            )



def test_16_short_and_rejected_delivery_only_adds_accepted_quantity_to_stock(runtime):
    from datetime import UTC, date, datetime
    from uuid import uuid4

    from retail_app.infrastructure.database import PostgresDatabase
    from retail_app.procurement.chain import (
        approve_purchase_order,
        get_stock_balance,
        receive_goods,
    )
    from retail_app.procurement.purchase_orders import PurchaseOrder, PurchaseOrderLine
    from retail_app.procurement.service import create_purchase_order, create_supplier
    from retail_app.procurement.suppliers import Supplier
    from retail_app.security.authorization import AccessContext, Role

    database = PostgresDatabase(RUNTIME_URL)
    actor = AccessContext(str(USER_A), str(TENANT_A), Role.OWNER_ADMIN)
    supplier_id, order_id, item_id = str(uuid4()), str(uuid4()), str(uuid4())
    create_supplier(
        database, actor, Supplier(supplier_id, str(TENANT_A), "Short Delivery Supplier"),
        idempotency_key="short-supplier-0001",
    )
    order = PurchaseOrder(
        id=order_id, tenant_id=str(TENANT_A), branch_id=str(BRANCH_A),
        supplier_id=supplier_id, currency="EUR", order_date=date(2026, 11, 8),
        lines=(PurchaseOrderLine(1, item_id, "Short delivery stock", 1500, 1000),),
        order_number="PO-SHORT-DELIVERY-0001",
    )
    create_purchase_order(database, actor, order, idempotency_key="short-po-0001")
    approve_purchase_order(database, actor, order_id, idempotency_key="short-approve-0001")
    receipt = receive_goods(
        database, actor, order_id, receipt_number="GR-SHORT-DELIVERY-0001",
        received_at=datetime(2026, 11, 8, tzinfo=UTC),
        lines=[{
            "po_line_number": 1, "received_quantity_milli": 1000,
            "accepted_quantity_milli": 800, "rejected_quantity_milli": 200,
            "discrepancy_code": "shortage",
            "discrepancy_note": "500 milli short; 200 milli rejected during quality check",
        }],
        idempotency_key="short-receipt-0001",
    )
    assert receipt["purchase_order_status"] == "partially_received"
    assert receipt["discrepancies"]
    stock = get_stock_balance(database, actor, branch_id=str(BRANCH_A), item_id=item_id)
    assert stock["on_hand_quantity_milli"] == 800



def test_14_session_bootstrap_lookup_is_narrow_and_runtime_cannot_read_table(runtime):
    with runtime.transaction():
        with pytest.raises(psycopg.errors.InsufficientPrivilege), runtime.transaction():
            runtime.execute("SELECT count(*) FROM auth_session_bootstrap")
        row = runtime.execute(
            """
            SELECT tenant_id, identity_id, session_id
            FROM resolve_auth_session_bootstrap(decode(repeat('01', 32), 'hex'))
            """
        ).fetchone()
        assert row == (TENANT_A, USER_A, SESSION_A)


def test_15_session_bootstrap_rejects_expired_and_revoked_sessions(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        runtime.execute(
            "UPDATE auth_sessions SET created_at = now() - interval '2 days', expires_at = now() - interval '1 second' WHERE id = %s",
            (SESSION_A,),
        )
        assert runtime.execute(
            "SELECT count(*) FROM resolve_auth_session_bootstrap(decode(repeat('01', 32), 'hex'))"
        ).fetchone()[0] == 0
        runtime.execute(
            "UPDATE auth_sessions SET expires_at = now() + interval '1 day', revoked_at = now() WHERE id = %s",
            (SESSION_A,),
        )
        assert runtime.execute(
            "SELECT count(*) FROM resolve_auth_session_bootstrap(decode(repeat('01', 32), 'hex'))"
        ).fetchone()[0] == 0


def test_16_bootstrap_owner_and_runtime_have_no_bypassrls(runtime):
    with runtime.transaction():
        rows = runtime.execute(
            """
            SELECT rolname, rolcanlogin, rolsuper, rolbypassrls
            FROM pg_roles WHERE rolname IN ('auth_bootstrap_owner', 'retail_runtime')
            ORDER BY rolname
            """
        ).fetchall()
        assert rows == [
            ("auth_bootstrap_owner", False, False, False),
            ("retail_runtime", True, False, False),
        ]


def _live_session(token: str, *, expires: str = "1 day", revoked: bool = False):
    from hashlib import sha256
    from uuid import uuid4

    session_id = uuid4()
    token_hash = sha256(token.encode("ascii")).digest()
    with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
        admin.execute(
            """
            INSERT INTO auth_sessions
                (id, tenant_id, identity_id, refresh_token_hash, created_at, expires_at, revoked_at)
            VALUES (%s, %s, %s, %s, now() - interval '2 days', now() + %s::interval,
                    CASE WHEN %s THEN now() ELSE NULL END)
            """,
            (session_id, TENANT_A, USER_A, token_hash, expires, revoked),
        )
    return session_id


def _resolve_live(token: str):
    from starlette.requests import Request

    from retail_app.api.session_resolver import PostgresSessionResolver
    from retail_app.infrastructure.database import PostgresDatabase

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/procurement/purchase-orders",
        "query_string": b"",
        "headers": [(b"cookie", f"__Host-retail_session={token}".encode("ascii"))],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
    })
    return PostgresSessionResolver(PostgresDatabase(RUNTIME_URL))(request)


def test_17_real_postgres_cookie_resolver_reads_current_role_and_branch_memberships():
    from secrets import token_urlsafe

    token = token_urlsafe(48)
    session_id = _live_session(token)
    try:
        context = _resolve_live(token)
        assert context.subject_id == str(USER_A)
        assert context.tenant_id == str(TENANT_A)
        assert context.role.value == "owner_admin"
        assert str(BRANCH_A) in context.branch_ids
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute("DELETE FROM auth_sessions WHERE id = %s", (session_id,))


@pytest.mark.parametrize("expired,revoked", [(True, False), (False, True)])
def test_18_real_postgres_resolver_denies_expired_or_revoked_sessions(expired, revoked):
    from secrets import token_urlsafe

    token = token_urlsafe(48)
    session_id = _live_session(token, expires="-1 second" if expired else "1 day", revoked=revoked)
    try:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as error:
            _resolve_live(token)
        assert error.value.status_code == 401
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute("DELETE FROM auth_sessions WHERE id = %s", (session_id,))


def test_19_real_postgres_resolver_denies_revoked_membership():
    from secrets import token_urlsafe

    from fastapi import HTTPException

    token = token_urlsafe(48)
    session_id = _live_session(token)
    with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
        admin.execute(
            "UPDATE tenant_memberships SET status = 'revoked' WHERE tenant_id = %s AND identity_id = %s",
            (TENANT_A, USER_A),
        )
    try:
        with pytest.raises(HTTPException) as error:
            _resolve_live(token)
        assert error.value.status_code == 403
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(
                "UPDATE tenant_memberships SET status = 'active' WHERE tenant_id = %s AND identity_id = %s",
                (TENANT_A, USER_A),
            )
            admin.execute("DELETE FROM auth_sessions WHERE id = %s", (session_id,))


def test_20_role_change_between_resolution_and_business_transaction_is_denied():
    from secrets import token_urlsafe

    from retail_app.infrastructure.database import PostgresDatabase

    token = token_urlsafe(48)
    session_id = _live_session(token)
    database = PostgresDatabase(RUNTIME_URL)
    try:
        context = _resolve_live(token)
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(
                "UPDATE tenant_memberships SET role = 'employee' WHERE tenant_id = %s AND identity_id = %s",
                (TENANT_A, USER_A),
            )
        with pytest.raises(PermissionError, match="role changed"), database.tenant_transaction(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            expected_role=context.role.value,
            expected_branch_ids=context.branch_ids,
            session_id=context.session_id,
            session_token_hash=context.session_token_hash,
        ):
            pass
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(
                "UPDATE tenant_memberships SET role = 'owner_admin' WHERE tenant_id = %s AND identity_id = %s",
                (TENANT_A, USER_A),
            )
            admin.execute("DELETE FROM auth_sessions WHERE id = %s", (session_id,))


def test_21_real_postgres_cross_tenant_and_branch_revocation_are_denied():
    from secrets import token_urlsafe

    from retail_app.infrastructure.database import PostgresDatabase

    token = token_urlsafe(48)
    session_id = _live_session(token)
    database = PostgresDatabase(RUNTIME_URL)
    try:
        context = _resolve_live(token)
        with database.tenant_transaction(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            expected_role=context.role.value,
            expected_branch_ids=context.branch_ids,
            session_id=context.session_id,
            session_token_hash=context.session_token_hash,
        ) as connection:
            assert connection.execute("SELECT id FROM tenants WHERE id = %s", (TENANT_B,)).fetchall() == []

        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(
                "UPDATE tenant_memberships SET role = 'branch_manager' WHERE tenant_id = %s AND identity_id = %s",
                (TENANT_A, USER_A),
            )
        branch_context = _resolve_live(token)
        assert str(BRANCH_A) in branch_context.branch_ids
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(
                """UPDATE branch_memberships SET status = 'revoked'
                   WHERE tenant_id = %s AND branch_id = %s AND identity_id = %s""",
                (TENANT_A, BRANCH_A, USER_A),
            )
        with pytest.raises(PermissionError, match="branch membership changed"), database.tenant_transaction(
            tenant_id=branch_context.tenant_id,
            subject_id=branch_context.subject_id,
            expected_role=branch_context.role.value,
            expected_branch_ids=branch_context.branch_ids,
            session_id=branch_context.session_id,
            session_token_hash=branch_context.session_token_hash,
        ):
            pass
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(
                "UPDATE branch_memberships SET status = 'active' WHERE tenant_id = %s AND branch_id = %s AND identity_id = %s",
                (TENANT_A, BRANCH_A, USER_A),
            )
            admin.execute(
                "UPDATE tenant_memberships SET role = 'owner_admin' WHERE tenant_id = %s AND identity_id = %s",
                (TENANT_A, USER_A),
            )
            admin.execute("DELETE FROM auth_sessions WHERE id = %s", (session_id,))

def test_22_real_postgres_resolver_denies_inactive_branch_even_with_active_membership():
    from secrets import token_urlsafe

    from retail_app.infrastructure.database import PostgresDatabase

    token = token_urlsafe(48)
    session_id = _live_session(token)
    database = PostgresDatabase(RUNTIME_URL)
    try:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(
                "UPDATE tenant_memberships SET role = 'branch_manager' "
                "WHERE tenant_id = %s AND identity_id = %s",
                (TENANT_A, USER_A),
            )
            admin.execute("UPDATE branches SET status = 'inactive' WHERE id = %s", (BRANCH_A,))
        context = _resolve_live(token)
        assert context.role.value == "branch_manager"
        assert str(BRANCH_A) not in context.branch_ids
        with pytest.raises(PermissionError, match="branch membership changed"), database.tenant_transaction(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            expected_role=context.role.value,
            expected_branch_ids=frozenset({str(BRANCH_A)}),
            session_id=context.session_id,
            session_token_hash=context.session_token_hash,
        ):
            pass
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute("UPDATE branches SET status = 'active' WHERE id = %s", (BRANCH_A,))
            admin.execute(
                "UPDATE tenant_memberships SET role = 'owner_admin' "
                "WHERE tenant_id = %s AND identity_id = %s",
                (TENANT_A, USER_A),
            )
            admin.execute("DELETE FROM auth_sessions WHERE id = %s", (session_id,))

def test_23_session_revocation_between_resolution_and_transaction_is_denied():
    from secrets import token_urlsafe

    from retail_app.infrastructure.database import PostgresDatabase

    token = token_urlsafe(48)
    session_id = _live_session(token)
    database = PostgresDatabase(RUNTIME_URL)
    try:
        context = _resolve_live(token)
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute("UPDATE auth_sessions SET revoked_at = now() WHERE id = %s", (session_id,))
        with pytest.raises(PermissionError, match="session is inactive or revoked"), database.tenant_transaction(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            expected_role=context.role.value,
            expected_branch_ids=context.branch_ids,
            session_id=context.session_id,
            session_token_hash=context.session_token_hash,
        ):
            pass
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute("DELETE FROM auth_sessions WHERE id = %s", (session_id,))
