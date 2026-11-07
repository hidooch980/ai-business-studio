from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.session import get_db_session
from backend.app.main import create_app


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("SESSION_LIFETIME_SECONDS", "3600")
    get_settings.cache_clear()

    engine = create_engine("sqlite://")

    @pytest.fixture
    def _unused() -> None:
        return None

    Base.metadata.create_all(engine)
    application = create_app()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine, expire_on_commit=False) as db:
            yield db

    application.dependency_overrides[get_db_session] = override_db
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def test_register_login_me_and_logout_cookie_flow(auth_client: TestClient) -> None:
    payload = {
        "email": "Owner@Example.test",
        "password": "correct horse battery staple",
        "display_name": "Studio Owner",
        "tenant_name": "Example Studio",
        "tenant_slug": "example-studio",
    }
    registered = auth_client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    assert registered.json()["user"]["email"] == "owner@example.test"
    assert len(registered.json()["memberships"]) == 1
    cookie = registered.cookies.get("abs_session")
    assert cookie
    assert "HttpOnly" in registered.headers["set-cookie"]
    assert "SameSite=lax" in registered.headers["set-cookie"]
    assert "Secure" not in registered.headers["set-cookie"]

    current = auth_client.get("/api/v1/auth/me")
    assert current.status_code == 200
    assert current.json()["user"]["id"] == registered.json()["user"]["id"]

    logout = auth_client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert auth_client.get("/api/v1/auth/me").status_code == 401

    login = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.test", "password": payload["password"]},
    )
    assert login.status_code == 200
    assert auth_client.get("/api/v1/auth/me").status_code == 200


def test_auth_api_rejects_invalid_credentials_and_duplicate_registration(auth_client: TestClient) -> None:
    payload = {
        "email": "duplicate@example.test",
        "password": "correct horse battery staple",
        "display_name": "Duplicate",
        "tenant_name": "Duplicate Studio",
        "tenant_slug": "duplicate-studio",
    }
    assert auth_client.post("/api/v1/auth/register", json=payload).status_code == 201
    duplicate = {**payload, "email": "DUPLICATE@example.test"}
    assert auth_client.post("/api/v1/auth/register", json=duplicate).status_code == 409
    invalid = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "duplicate@example.test", "password": "not the password"},
    )
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Invalid email or password"}


def test_public_registration_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "false")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    application = create_app()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine, expire_on_commit=False) as db:
            yield db

    application.dependency_overrides[get_db_session] = override_db
    try:
        with TestClient(application) as client:
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "blocked@example.test",
                    "password": "correct horse battery staple",
                    "display_name": "Blocked",
                    "tenant_name": "Blocked Studio",
                    "tenant_slug": "blocked-studio",
                },
            )
        assert response.status_code == 403
    finally:
        application.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()
