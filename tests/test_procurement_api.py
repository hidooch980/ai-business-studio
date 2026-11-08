import os
import subprocess
import sys
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import build_engine, get_db_session
from backend.app.main import create_app


@pytest.fixture
def procurement_client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    database_url = f"sqlite:///{tmp_path / 'procurement.db'}"
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


def test_procurement_preview_is_tenant_authorized_and_never_creates_a_purchase_order(
    procurement_client: TestClient,
) -> None:
    registered = procurement_client.post(
        "/api/v1/auth/register",
        json={
            "email": "procurement-owner@example.test",
            "password": "correct horse battery staple",
            "display_name": "Procurement Owner",
            "tenant_name": "Procurement Studio",
            "tenant_slug": "procurement-studio",
        },
    )
    assert registered.status_code == 201, registered.text
    tenant_id = registered.json()["memberships"][0]["tenant_id"]
    upgrade = procurement_client.put(
        "/api/v1/modules/edition",
        json={"edition": "growth"},
        headers={
            "X-Tenant-ID": tenant_id,
            "X-CSRF-Token": procurement_client.cookies.get("abs_csrf"),
        },
    )
    assert upgrade.status_code == 200, upgrade.text
    payload = {
        "product_id": "b8d1d61d-00a1-4a0e-9b7b-3f9c1f7e2a10",
        "warehouse_id": "1cfd4e88-89e0-45a8-a6c2-55db2f7c1c01",
        "demand_history": [{"units": "10"} for _ in range(30)],
        "sellable_on_hand": "5",
        "lead_time_days": 3,
        "review_period_days": 7,
        "minimum_order_quantity": "5",
        "order_multiple": "5",
        "budget_minor": 25000,
        "suppliers": [
            {
                "supplier_id": "supplier-a",
                "unit_cost_minor": 100,
                "freight_per_unit_minor": 5,
                "lead_time_days": 3,
                "on_time_rate": "0.98",
                "quality_acceptance_rate": "0.99",
                "capacity_units": "60",
                "approved": True,
            },
            {
                "supplier_id": "blocked-supplier",
                "unit_cost_minor": 1,
                "approved": False,
            },
        ],
        "source_branches": [
            {
                "branch_id": "branch-west",
                "sellable_units": "20",
                "reserved_units": "2",
                "safety_stock_units": "5",
            }
        ],
    }
    response = procurement_client.post(
        "/api/v1/procurement/preview",
        json=payload,
        headers={"X-Tenant-ID": tenant_id},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["selected_supplier_id"] == "supplier-a"
    assert result["suggested_transfer_quantity"] == "13"
    assert result["suggested_purchase_quantity"] == "47"
    assert result["estimated_cost_minor"] == 4935
    assert result["requires_human_approval"] is True
    assert result["creates_purchase_order"] is False
    assert len(result["supplier_candidates"]) == 1


def test_procurement_preview_rejects_invalid_order_multiple(procurement_client: TestClient) -> None:
    registered = procurement_client.post(
        "/api/v1/auth/register",
        json={
            "email": "procurement-invalid@example.test",
            "password": "correct horse battery staple",
            "display_name": "Procurement Invalid",
            "tenant_name": "Procurement Invalid Studio",
            "tenant_slug": "procurement-invalid",
        },
    )
    assert registered.status_code == 201
    tenant_id = registered.json()["memberships"][0]["tenant_id"]
    upgrade = procurement_client.put(
        "/api/v1/modules/edition",
        json={"edition": "growth"},
        headers={
            "X-Tenant-ID": tenant_id,
            "X-CSRF-Token": procurement_client.cookies.get("abs_csrf"),
        },
    )
    assert upgrade.status_code == 200, upgrade.text
    response = procurement_client.post(
        "/api/v1/procurement/preview",
        json={
            "product_id": "b8d1d61d-00a1-4a0e-9b7b-3f9c1f7e2a10",
            "warehouse_id": "1cfd4e88-89e0-45a8-a6c2-55db2f7c1c01",
            "demand_history": [{"units": "1"}],
            "sellable_on_hand": "0",
            "lead_time_days": 1,
            "order_multiple": "0",
        },
        headers={"X-Tenant-ID": tenant_id},
    )
    assert response.status_code == 422
