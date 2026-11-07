import os
import subprocess
import sys
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid import UUID

from backend.app.core.config import get_settings
from backend.app.db.session import build_engine, get_db_session
from backend.app.main import create_app
from backend.app.outbox.models import OutboxEvent


@pytest.fixture
def inventory_client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    database_url = f"sqlite:///{tmp_path / 'inventory.db'}"
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


def _register(client: TestClient, email: str, tenant_slug: str) -> tuple[str, str]:
    csrf_token = client.cookies.get("abs_csrf")
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "Inventory Owner",
            "tenant_name": "Inventory Studio",
            "tenant_slug": tenant_slug,
        },
        headers={"X-CSRF-Token": csrf_token} if csrf_token else None,
    )
    assert response.status_code == 201, response.text
    return response.json()["memberships"][0]["tenant_id"], client.cookies.get("abs_csrf", "")


def _headers(client: TestClient, tenant_id: str, csrf: str) -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id, "X-CSRF-Token": csrf}


def test_inventory_receipt_issue_idempotency_and_nonnegative_stock(inventory_client: TestClient) -> None:
    tenant_id, csrf = _register(inventory_client, "stock-owner@example.test", "stock-studio")
    headers = _headers(inventory_client, tenant_id, csrf)

    warehouse_response = inventory_client.post(
        "/api/v1/inventory/warehouses",
        json={"code": "MAIN", "name": "Main warehouse"},
        headers=headers,
    )
    assert warehouse_response.status_code == 201, warehouse_response.text
    warehouse_id = warehouse_response.json()["id"]

    product_response = inventory_client.post(
        "/api/v1/catalog/products",
        json={"sku": "ITEM-001", "name": "Sample item", "unit_code": "pcs"},
        headers=headers,
    )
    assert product_response.status_code == 201, product_response.text
    product_id = product_response.json()["id"]

    receipt = inventory_client.post(
        "/api/v1/inventory/movements",
        json={
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "movement_type": "receipt",
            "quantity": 10,
            "reference": "PO-100",
        },
        headers={**headers, "Idempotency-Key": "receipt-100"},
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["quantity_delta"] == 10
    assert receipt.json()["replayed"] is False

    replay = inventory_client.post(
        "/api/v1/inventory/movements",
        json={
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "movement_type": "receipt",
            "quantity": 10,
            "reference": "PO-100",
        },
        headers={**headers, "Idempotency-Key": "receipt-100"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == receipt.json()["id"]
    assert replay.json()["replayed"] is True

    issue = inventory_client.post(
        "/api/v1/inventory/movements",
        json={
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "movement_type": "issue",
            "quantity": 4,
        },
        headers={**headers, "Idempotency-Key": "issue-101"},
    )
    assert issue.status_code == 201, issue.text
    assert issue.json()["quantity_delta"] == -4

    insufficient = inventory_client.post(
        "/api/v1/inventory/movements",
        json={
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "movement_type": "issue",
            "quantity": 7,
        },
        headers={**headers, "Idempotency-Key": "issue-too-much"},
    )
    assert insufficient.status_code == 409

    balances = inventory_client.get("/api/v1/inventory/balances", headers=headers)
    assert balances.status_code == 200
    assert balances.json()["items"][0]["quantity_on_hand"] == 6

    movements = inventory_client.get("/api/v1/inventory/movements", headers=headers)
    assert movements.status_code == 200
    assert len(movements.json()["items"]) == 2
    with Session(inventory_client.app.state.test_engine) as db:
        outbox_events = db.query(OutboxEvent).filter_by(tenant_id=UUID(tenant_id)).all()
        assert len(outbox_events) == 2
        assert {item.event_type for item in outbox_events} == {"inventory.movement.created"}


def test_inventory_rejects_cross_tenant_warehouse_and_product(inventory_client: TestClient) -> None:
    first_tenant, first_csrf = _register(inventory_client, "first-owner@example.test", "first-stock")
    first_headers = _headers(inventory_client, first_tenant, first_csrf)
    warehouse = inventory_client.post(
        "/api/v1/inventory/warehouses",
        json={"code": "FIRST", "name": "First tenant"},
        headers=first_headers,
    )
    product = inventory_client.post(
        "/api/v1/catalog/products",
        json={"sku": "FIRST-ITEM", "name": "First item"},
        headers=first_headers,
    )
    assert warehouse.status_code == 201
    assert product.status_code == 201

    inventory_client.cookies.clear()
    second_tenant, second_csrf = _register(inventory_client, "second-owner@example.test", "second-stock")
    second_headers = _headers(inventory_client, second_tenant, second_csrf)
    denied = inventory_client.post(
        "/api/v1/inventory/movements",
        json={
            "warehouse_id": warehouse.json()["id"],
            "product_id": product.json()["id"],
            "movement_type": "receipt",
            "quantity": 1,
        },
        headers={**second_headers, "Idempotency-Key": "cross-tenant"},
    )
    assert denied.status_code == 404
