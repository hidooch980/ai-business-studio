import os
import subprocess
import sys
from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import build_engine, get_db_session
from backend.app.identity.models import AuditEvent
from backend.app.inventory.models import InventoryMovement
from backend.app.main import create_app
from backend.app.procurement.models import ProcurementReceipt, PurchaseOrder


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


def _register_growth(client: TestClient) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "purchase-owner@example.test",
            "password": "correct horse battery staple",
            "display_name": "Purchase Owner",
            "tenant_name": "Purchase Studio",
            "tenant_slug": "purchase-studio",
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



def test_supplier_invoice_three_way_match_and_quantity_reservation(
    purchasing_client: TestClient,
) -> None:
    _, headers = _register_growth(purchasing_client)
    supplier = purchasing_client.post(
        "/api/v1/procurement/suppliers",
        json={"code": "SUP-INV", "name": "Invoice Supplier"},
        headers=headers,
    )
    product = purchasing_client.post(
        "/api/v1/catalog/products",
        json={"sku": "INV-001", "name": "Invoice Item", "unit_code": "pcs"},
        headers=headers,
    )
    warehouse = purchasing_client.post(
        "/api/v1/inventory/warehouses",
        json={"code": "INV-MAIN", "name": "Invoice warehouse"},
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
                "quantity": 10,
                "unit_cost_minor": 1500,
            }],
        },
        headers=headers,
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    order_line_id = order.json()["lines"][0]["id"]
    approved = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order_id}/approve",
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    receipt = purchasing_client.post(
        f"/api/v1/procurement/purchase-orders/{order_id}/receipts",
        json={"lines": [{"purchase_order_line_id": order_line_id, "quantity": 5}]},
        headers={**headers, "Idempotency-Key": "invoice-test-receipt"},
    )
    assert receipt.status_code == 201, receipt.text

    invoice_payload = {
        "purchase_order_id": order_id,
        "invoice_number": "SUP-INV-2026-001",
        "invoice_date": "2026-11-08",
        "due_date": "2026-12-08",
        "currency": "USD",
        "tax_minor": 200,
        "freight_minor": 50,
        "discount_minor": 100,
        "lines": [{
            "purchase_order_line_id": order_line_id,
            "quantity": 4,
            "unit_cost_minor": 1500,
        }],
    }
    invoice = purchasing_client.post(
        "/api/v1/procurement/supplier-invoices",
        json=invoice_payload,
        headers=headers,
    )
    assert invoice.status_code == 201, invoice.text
    invoice_data = invoice.json()
    assert invoice_data["status"] == "matched"
    assert invoice_data["subtotal_minor"] == 6000
    assert invoice_data["total_minor"] == 6150

    overbilled = purchasing_client.post(
        "/api/v1/procurement/supplier-invoices",
        json={
            **invoice_payload,
            "invoice_number": "SUP-INV-2026-002",
            "lines": [{
                "purchase_order_line_id": order_line_id,
                "quantity": 2,
                "unit_cost_minor": 1500,
            }],
        },
        headers=headers,
    )
    assert overbilled.status_code == 409

    price_mismatch = purchasing_client.post(
        "/api/v1/procurement/supplier-invoices",
        json={
            **invoice_payload,
            "invoice_number": "SUP-INV-2026-003",
            "lines": [{
                "purchase_order_line_id": order_line_id,
                "quantity": 1,
                "unit_cost_minor": 1400,
            }],
        },
        headers=headers,
    )
    assert price_mismatch.status_code == 409

    voided = purchasing_client.post(
        f"/api/v1/procurement/supplier-invoices/{invoice_data['id']}/void",
        headers=headers,
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["status"] == "void"

    replacement = purchasing_client.post(
        "/api/v1/procurement/supplier-invoices",
        json={
            **invoice_payload,
            "invoice_number": "SUP-INV-2026-004",
            "lines": [{
                "purchase_order_line_id": order_line_id,
                "quantity": 5,
                "unit_cost_minor": 1500,
            }],
        },
        headers=headers,
    )
    assert replacement.status_code == 201, replacement.text
    approved_invoice = purchasing_client.post(
        f"/api/v1/procurement/supplier-invoices/{replacement.json()['id']}/approve",
        headers=headers,
    )
    assert approved_invoice.status_code == 200, approved_invoice.text
    assert approved_invoice.json()["status"] == "approved"

    balances = purchasing_client.get("/api/v1/inventory/balances", headers=headers)
    assert balances.status_code == 200, balances.text
    assert balances.json()["items"][0]["quantity_on_hand"] == 5
