import os
import subprocess
import sys
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import build_engine, get_db_session
from backend.app.identity.models import AuditEvent
from backend.app.inventory.models import InventoryMovement
from backend.app.main import create_app
from backend.app.procurement.models import (
    ProcurementReceipt,
    PurchaseOrder,
    SupplierInvoice,
    SupplierPayment,
)


@pytest.fixture
def purchasing_client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    database_url = f"sqlite:///{tmp_path / 'purchasing.db'}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert migration.returncode == 0, f"{migration.stdout}\n{migration.stderr}"
    engine = build_engine(database_url)
    application = create_app()
    application.state.test_engine = engine

    def override_db() -> Generator[Session, None, None]:
        with Session(engine, expire_on_commit=False) as db:
            yield db

    application.dependency_overrides[get_db_session] = override_db
    try:
        with TestClient(application) as client:
            client.headers.update({"Origin": str(client.base_url).rstrip("/")})
            yield client
    finally:
        application.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def _register_growth(client: TestClient, suffix: str = "") -> tuple[str, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"purchase-owner{suffix}@example.test",
            "password": "correct horse battery staple",
            "display_name": "Purchase Owner",
            "tenant_name": f"Purchase Studio{suffix}",
            "tenant_slug": f"purchase-studio{suffix or '-main'}",
        },
    )
    assert response.status_code == 201, response.text
    tenant_id = response.json()["memberships"][0]["tenant_id"]
    headers = {
        "X-Tenant-ID": tenant_id,
        "X-CSRF-Token": client.cookies.get("abs_csrf"),
    }
    upgraded = client.put("/api/v1/modules/edition", json={"edition": "growth"}, headers=headers)
    assert upgraded.status_code == 200, upgraded.text
    return tenant_id, headers


def test_purchase_to_stock_partial_receipt_and_idempotency(purchasing_client: TestClient) -> None:
    tenant_id, headers = _register_growth(purchasing_client)
    tenant_uuid = UUID(tenant_id)

    supplier = purchasing_client.post(
        "/api/v1/procurement/suppliers",
        json={"code": "SUP-01", "name": "Primary Supplier", "payment_terms_days": 30},
        headers=headers,
    )
    assert supplier.status_code == 201, supplier.text

    product = purchasing_client.post(
        "/api/v1/catalog/products",
        json={"sku": "PUR-001", "name": "Purchase Item", "unit_code": "pcs"},
        headers=headers,
    )
    assert product.status_code == 201, product.text

    warehouse = purchasing_client.post(
        "/api/v1/inventory/warehouses",
        json={"code": "MAIN", "name": "Main warehouse"},
        headers=headers,
    )
    assert warehouse.status_code == 201, warehouse.text

    order = purchasing_client.post(
        "/api/v1/procurement/purchase-orders",
        json={
            "supplier_id": supplier.json()["id"],
            "warehouse_id": warehouse.json()["id"],
            "lines": [{
                "product_id": product.json()["id"],
                "quantity": 8,
                "unit_cost_minor": 1250,
            }],
        },
        headers=headers,
    )
    assert order.status_code == 201, order.text
    order_data = order.json()
    assert order_data["status"] == "draft"
    line_id = order_data["lines"][0]["id"]

    approved = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order_data['id']}/approve",
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    receipt_payload = {"lines": [{"purchase_order_line_id": line_id, "quantity": 3}]}
    receipt_headers = {**headers, "Idempotency-Key": "receipt-part-1"}
    first_receipt = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order_data['id']}/receipts",
        json=receipt_payload,
        headers=receipt_headers,
    )
    assert first_receipt.status_code == 201, first_receipt.text
    assert first_receipt.json()["status"] == "partially_received"

    replay = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order_data['id']}/receipts",
        json=receipt_payload,
        headers=receipt_headers,
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["replayed"] is True

    def replay_receipt() -> tuple[int, bool]:
        response = purchasing_client.post(
            f"/api/v1/procurement/purchase-orders/{order_data['id']}/receipts",
            json=receipt_payload,
            headers=receipt_headers,
        )
        return response.status_code, response.json().get("replayed", False)

    with ThreadPoolExecutor(max_workers=6) as pool:
        concurrent_replays = list(pool.map(lambda _: replay_receipt(), range(6)))
    assert concurrent_replays == [(201, True)] * 6

    conflicting_replay = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order_data['id']}/receipts",
        json={"lines": [{"purchase_order_line_id": line_id, "quantity": 4}]},
        headers=receipt_headers,
    )
    assert conflicting_replay.status_code == 409

    final_receipt = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order_data['id']}/receipts",
        json={"lines": [{"purchase_order_line_id": line_id, "quantity": 5}]},
        headers={**headers, "Idempotency-Key": "receipt-part-2"},
    )
    assert final_receipt.status_code == 201, final_receipt.text
    assert final_receipt.json()["status"] == "received"

    balances = purchasing_client.get("/api/v1/inventory/balances", headers=headers)
    assert balances.status_code == 200, balances.text
    assert len(balances.json()["items"]) == 1
    assert balances.json()["items"][0]["quantity_on_hand"] == 8

    with Session(purchasing_client.app.state.test_engine) as db:
        saved_order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_uuid))
        movements = db.scalars(select(InventoryMovement).where(
            InventoryMovement.tenant_id == tenant_uuid,
            InventoryMovement.reference.like(f"{order_data['order_number']}/receipt/%"),
        )).all()
        receipts = db.scalars(select(ProcurementReceipt).where(
            ProcurementReceipt.tenant_id == tenant_uuid,
        )).all()
        audits = db.scalars(select(AuditEvent).where(
            AuditEvent.tenant_id == tenant_uuid,
            AuditEvent.action.in_([
                "procurement.purchase_order_created",
                "procurement.purchase_order_approved",
                "procurement.goods_received",
            ]),
        )).all()
        assert saved_order is not None and saved_order.status == "received"
        assert len(movements) == 2
        assert len(receipts) == 2
        assert len(audits) == 4


def test_purchase_order_cannot_be_received_before_approval(purchasing_client: TestClient) -> None:
    _, headers = _register_growth(purchasing_client)
    supplier = purchasing_client.post(
        "/api/v1/procurement/suppliers",
        json={"code": "SUP-02", "name": "Secondary Supplier"},
        headers=headers,
    )
    product = purchasing_client.post(
        "/api/v1/catalog/products",
        json={"sku": "PUR-002", "name": "Unapproved Item"},
        headers=headers,
    )
    warehouse = purchasing_client.post(
        "/api/v1/inventory/warehouses",
        json={"code": "SEC", "name": "Secondary warehouse"},
        headers=headers,
    )
    assert supplier.status_code == product.status_code == warehouse.status_code == 201
    order = purchasing_client.post(
        "/api/v1/procurement/purchase-orders",
        json={
            "supplier_id": supplier.json()["id"],
            "warehouse_id": warehouse.json()["id"],
            "lines": [{
                "product_id": product.json()["id"],
                "quantity": 2,
                "unit_cost_minor": 100,
            }],
        },
        headers=headers,
    )
    assert order.status_code == 201
    line_id = order.json()["lines"][0]["id"]
    response = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order.json()['id']}/receipts",
        json={"lines": [{"purchase_order_line_id": line_id, "quantity": 1}]},
        headers={**headers, "Idempotency-Key": "unapproved-receipt"},
    )
    assert response.status_code == 409


def test_supplier_data_is_isolated_between_tenants(purchasing_client: TestClient) -> None:
    _, tenant_a_headers = _register_growth(purchasing_client, "-a")
    with TestClient(purchasing_client.app) as tenant_b_client:
        tenant_b_client.headers.update({"Origin": str(tenant_b_client.base_url).rstrip("/")})
        _, tenant_b_headers = _register_growth(tenant_b_client, "-b")
        created = tenant_b_client.post(
            "/api/v1/procurement/suppliers",
            json={"code": "PRIVATE-B", "name": "Tenant B private supplier"},
            headers=tenant_b_headers,
        )
        assert created.status_code == 201, created.text

        visible_to_a = purchasing_client.get(
            "/api/v1/procurement/suppliers", headers=tenant_a_headers
        )
        visible_to_b = tenant_b_client.get(
            "/api/v1/procurement/suppliers", headers=tenant_b_headers
        )
        assert visible_to_a.status_code == 200, visible_to_a.text
        assert visible_to_a.json()["items"] == []
        assert visible_to_b.status_code == 200, visible_to_b.text
        assert [item["id"] for item in visible_to_b.json()["items"]] == [created.json()["id"]]

        forbidden_tenant_switch = purchasing_client.get(
            "/api/v1/procurement/suppliers",
            headers={**tenant_a_headers, "X-Tenant-ID": tenant_b_headers["X-Tenant-ID"]},
        )
        assert forbidden_tenant_switch.status_code == 403



def test_purchase_to_pay_three_way_match_and_partial_payment(purchasing_client: TestClient) -> None:
    tenant_id, headers = _register_growth(purchasing_client, "-payables")
    supplier = purchasing_client.post(
        "/api/v1/procurement/suppliers",
        json={"code": "PAY-SUP", "name": "Payables Supplier"},
        headers=headers,
    )
    product = purchasing_client.post(
        "/api/v1/catalog/products",
        json={"sku": "PAY-001", "name": "Payables Item", "unit_code": "pcs"},
        headers=headers,
    )
    warehouse = purchasing_client.post(
        "/api/v1/inventory/warehouses",
        json={"code": "PAY-WH", "name": "Payables Warehouse"},
        headers=headers,
    )
    assert supplier.status_code == product.status_code == warehouse.status_code == 201

    order = purchasing_client.post(
        "/api/v1/procurement/purchase-orders",
        json={
            "supplier_id": supplier.json()["id"],
            "warehouse_id": warehouse.json()["id"],
            "lines": [{
                "product_id": product.json()["id"],
                "quantity": 3,
                "unit_cost_minor": 1250,
            }],
        },
        headers=headers,
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    approved = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order_id}/approve",
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    line_id = order.json()["lines"][0]["id"]
    received = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order_id}/receipts",
        json={"lines": [{"purchase_order_line_id": line_id, "quantity": 3}]},
        headers={**headers, "Idempotency-Key": "payables-receipt-1"},
    )
    assert received.status_code == 201, received.text

    invoice = purchasing_client.post(
        "/api/v1/procurement/payables/invoices",
        json={
            "supplier_id": supplier.json()["id"],
            "purchase_order_id": order_id,
            "invoice_number": "INV-2026-001",
            "invoice_date": "2026-11-08",
            "due_date": "2026-12-08",
            "currency": "USD",
            "lines": [{
                "purchase_order_line_id": line_id,
                "quantity": 3,
                "unit_cost_minor": 1250,
            }],
        },
        headers=headers,
    )
    assert invoice.status_code == 201, invoice.text
    invoice_id = invoice.json()["id"]

    matched = purchasing_client.post(
        f"/api/v1/procurement/payables/invoices/{invoice_id}/match",
        headers=headers,
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["total_minor"] == 3750
    assert matched.json()["status"] == "matched"

    approved_invoice = purchasing_client.post(
        f"/api/v1/procurement/payables/invoices/{invoice_id}/approve",
        headers=headers,
    )
    assert approved_invoice.status_code == 200, approved_invoice.text
    posted = purchasing_client.post(
        f"/api/v1/procurement/payables/invoices/{invoice_id}/post",
        headers=headers,
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "posted"

    first_payment_payload = {
        "amount_minor": 1000,
        "currency": "USD",
        "payment_date": "2026-11-08",
        "payment_reference": "BANK-TRANSFER-001",
    }
    payment_headers = {**headers, "Idempotency-Key": "payables-payment-1"}
    payment = purchasing_client.post(
        f"/api/v1/procurement/payables/invoices/{invoice_id}/payments",
        json=first_payment_payload,
        headers=payment_headers,
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["outstanding_minor"] == 2750
    assert payment.json()["status"] == "partially_paid"

    replay = purchasing_client.post(
        f"/api/v1/procurement/payables/invoices/{invoice_id}/payments",
        json=first_payment_payload,
        headers=payment_headers,
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["replayed"] is True

    final_payment = purchasing_client.post(
        f"/api/v1/procurement/payables/invoices/{invoice_id}/payments",
        json={
            "amount_minor": 2750,
            "currency": "USD",
            "payment_date": "2026-11-08",
            "payment_reference": "BANK-TRANSFER-002",
        },
        headers={**headers, "Idempotency-Key": "payables-payment-2"},
    )
    assert final_payment.status_code == 201, final_payment.text
    assert final_payment.json()["outstanding_minor"] == 0
    assert final_payment.json()["status"] == "paid"

    with Session(purchasing_client.app.state.test_engine) as db:
        saved_invoice = db.scalar(
            select(SupplierInvoice).where(SupplierInvoice.tenant_id == UUID(tenant_id))
        )
        payments = db.scalars(
            select(SupplierPayment).where(SupplierPayment.tenant_id == UUID(tenant_id))
        ).all()
        assert saved_invoice is not None
        assert saved_invoice.total_minor == 3750
        assert saved_invoice.paid_minor == 3750
        assert saved_invoice.status == "paid"
        assert len(payments) == 2



@pytest.fixture
def postgres_purchasing_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    source_url = os.environ.get("DATABASE_URL", "")
    if not source_url.startswith("postgresql"):
        pytest.skip("PostgreSQL concurrency test requires DATABASE_URL")
    database_name = f"abs_concurrency_{uuid4().hex[:12]}"
    admin_engine = create_engine(source_url)
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    database_url = make_url(source_url).set(database=database_name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert migration.returncode == 0, f"{migration.stdout}\n{migration.stderr}"
    engine = build_engine(database_url)
    application = create_app()
    application.state.test_engine = engine

    def override_db() -> Generator[Session, None, None]:
        with Session(engine, expire_on_commit=False) as db:
            yield db

    application.dependency_overrides[get_db_session] = override_db
    try:
        with TestClient(application) as client:
            client.headers.update({"Origin": str(client.base_url).rstrip("/")})
            yield client
    finally:
        application.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        admin_engine.dispose()



def test_postgres_rejects_concurrent_over_receipt(
    postgres_purchasing_client: TestClient,
) -> None:
    client = postgres_purchasing_client
    _, headers = _register_growth(client, "-concurrency")
    supplier = client.post(
        "/api/v1/procurement/suppliers",
        json={"code": "RACE-SUP", "name": "Concurrency Supplier"},
        headers=headers,
    )
    product = client.post(
        "/api/v1/catalog/products",
        json={"sku": "RACE-001", "name": "Concurrency Item", "unit_code": "pcs"},
        headers=headers,
    )
    warehouse = client.post(
        "/api/v1/inventory/warehouses",
        json={"code": "RACE-WH", "name": "Concurrency Warehouse"},
        headers=headers,
    )
    assert supplier.status_code == product.status_code == warehouse.status_code == 201
    order = client.post(
        "/api/v1/procurement/purchase-orders",
        json={
            "supplier_id": supplier.json()["id"],
            "warehouse_id": warehouse.json()["id"],
            "lines": [{
                "product_id": product.json()["id"],
                "quantity": 5,
                "unit_cost_minor": 100,
            }],
        },
        headers=headers,
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    line_id = order.json()["lines"][0]["id"]
    approved = client.post(
        f"/api/v1/procurement/purchase-orders/{order_id}/approve",
        headers=headers,
    )
    assert approved.status_code == 200, approved.text

    def receive(key: str) -> int:
        response = client.post(
            f"/api/v1/procurement/purchase-orders/{order_id}/receipts",
            json={"lines": [{"purchase_order_line_id": line_id, "quantity": 4}]},
            headers={**headers, "Idempotency-Key": key},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(receive, ["parallel-receipt-a", "parallel-receipt-b"]))
    assert results == [201, 409]

    balances = client.get("/api/v1/inventory/balances", headers=headers)
    assert balances.status_code == 200, balances.text
    assert balances.json()["items"][0]["quantity_on_hand"] == 4
