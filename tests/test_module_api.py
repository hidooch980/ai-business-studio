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
def module_client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    database_url = f"sqlite:///{tmp_path / 'modules.db'}"
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


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "Module Owner",
            "tenant_name": "Module Studio",
            "tenant_slug": email.split("@")[0],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["memberships"][0]["tenant_id"]


def _write_headers(client: TestClient, tenant_id: str) -> dict[str, str]:
    return {
        "X-Tenant-ID": tenant_id,
        "X-CSRF-Token": client.cookies.get("abs_csrf"),
    }


def test_tenant_module_entitlements_upgrade_and_safe_disable(module_client: TestClient) -> None:
    tenant_id = _register(module_client, "modules-owner@example.test")
    headers = {"X-Tenant-ID": tenant_id}

    initial = module_client.get("/api/v1/modules", headers=headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["edition"] == "starter"
    initial_modules = {item["module_id"]: item for item in initial.json()["modules"]}
    assert initial_modules["inventory"]["is_enabled"] is True
    assert initial_modules["procurement"]["is_entitled"] is False

    upgrade = module_client.put(
        "/api/v1/modules/edition",
        json={"edition": "growth"},
        headers=_write_headers(module_client, tenant_id),
    )
    assert upgrade.status_code == 200, upgrade.text

    upgraded = module_client.get("/api/v1/modules", headers=headers)
    modules = {item["module_id"]: item for item in upgraded.json()["modules"]}
    assert modules["procurement"]["is_entitled"] is True
    assert modules["procurement"]["is_enabled"] is True
    assert modules["sales"]["is_entitled"] is True
    assert modules["sales"]["is_enabled"] is False

    blocked_disable = module_client.put(
        "/api/v1/modules/inventory",
        json={"is_enabled": False},
        headers=_write_headers(module_client, tenant_id),
    )
    assert blocked_disable.status_code == 409
    assert "dependent_modules" in blocked_disable.json()["detail"]

    disable_procurement = module_client.put(
        "/api/v1/modules/procurement",
        json={"is_enabled": False},
        headers=_write_headers(module_client, tenant_id),
    )
    assert disable_procurement.status_code == 200
    disabled = module_client.get("/api/v1/modules", headers=headers)
    disabled_modules = {item["module_id"]: item for item in disabled.json()["modules"]}
    assert disabled_modules["procurement"]["is_entitled"] is True
    assert disabled_modules["procurement"]["is_enabled"] is False


def test_tenant_module_management_is_tenant_scoped(module_client: TestClient) -> None:
    first_tenant = _register(module_client, "first-owner@example.test")
    second_tenant = _register(module_client, "second-owner@example.test")
    response = module_client.get(
        "/api/v1/modules",
        headers={"X-Tenant-ID": first_tenant},
    )
    assert response.status_code == 403
    assert second_tenant != first_tenant


def test_planned_module_cannot_be_enabled(module_client: TestClient) -> None:
    tenant_id = _register(module_client, "planned-owner@example.test")
    response = module_client.put(
        "/api/v1/modules/sales",
        json={"is_enabled": True},
        headers=_write_headers(module_client, tenant_id),
    )
    assert response.status_code == 409
