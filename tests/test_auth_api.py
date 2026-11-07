from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_permission
from backend.app.identity.models import Membership, MembershipRole, Permission, Role, RolePermission, Tenant
from backend.app.main import create_app


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("SESSION_LIFETIME_SECONDS", "3600")
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)
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
    cookie_header = registered.headers["set-cookie"].casefold()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header
    assert "secure" not in cookie_header
    csrf_token = auth_client.cookies.get("abs_csrf")
    assert csrf_token
    csrf_cookie_header = registered.headers.get_list("set-cookie")[1].casefold()
    assert "httponly" not in csrf_cookie_header

    current = auth_client.get("/api/v1/auth/me")
    assert current.status_code == 200
    assert current.json()["user"]["id"] == registered.json()["user"]["id"]

    rejected_logout = auth_client.post("/api/v1/auth/logout")
    assert rejected_logout.status_code == 403
    untrusted_origin = auth_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token, "Origin": "https://attacker.example"},
    )
    assert untrusted_origin.status_code == 403
    assert auth_client.get("/api/v1/auth/me").status_code == 200

    logout = auth_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
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
    csrf_token = auth_client.cookies.get("abs_csrf")
    assert auth_client.post(
        "/api/v1/auth/register",
        json=duplicate,
        headers={"X-CSRF-Token": csrf_token},
    ).status_code == 409
    invalid = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "duplicate@example.test", "password": "not the password"},
        headers={"X-CSRF-Token": csrf_token},
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


def test_login_rate_limit_locks_after_eight_failures(auth_client: TestClient) -> None:
    payload = {
        "email": "rate-limit@example.test",
        "password": "correct horse battery staple",
        "display_name": "Rate Limit",
        "tenant_name": "Rate Limit Studio",
        "tenant_slug": "rate-limit-studio",
    }
    assert auth_client.post("/api/v1/auth/register", json=payload).status_code == 201
    csrf_token = auth_client.cookies.get("abs_csrf")
    assert csrf_token
    for attempt in range(8):
        response = auth_client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": "incorrect password"},
            headers={"X-CSRF-Token": csrf_token},
        )
        expected_status = 429 if attempt == 7 else 401
        assert response.status_code == expected_status
    blocked = auth_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert blocked.status_code == 429


def test_production_rejects_placeholder_rate_limit_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "replace-with-a-long-random-secret")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="AUTH_RATE_LIMIT_SECRET"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_rbac_is_tenant_scoped_and_requires_assigned_permission(auth_client: TestClient) -> None:
    payload = {
        "email": "rbac@example.test",
        "password": "correct horse battery staple",
        "display_name": "RBAC User",
        "tenant_name": "Primary Tenant",
        "tenant_slug": "primary-tenant",
    }
    registered = auth_client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    tenant_id = registered.json()["memberships"][0]["tenant_id"]
    session_token = registered.cookies.get("abs_session")
    assert session_token
    auth_headers = {"Cookie": f"abs_session={session_token}"}

    router = APIRouter()

    @router.get("/rbac-probe")
    def rbac_probe(
        principal: TenantPrincipal = Depends(require_permission("reports.read")),
    ) -> dict:
        return {"tenant_id": str(principal.tenant.id), "membership_id": str(principal.membership.id)}

    auth_client.app.include_router(router, prefix="/api/v1/test")

    with Session(auth_client.app.state.test_engine) as db:
        membership = db.query(Membership).filter_by(tenant_id=UUID(tenant_id)).one()
        db.query(MembershipRole).filter_by(membership_id=membership.id).delete()
        db.commit()

    denied = auth_client.get(
        "/api/v1/test/rbac-probe",
        headers={**auth_headers, "X-Tenant-ID": tenant_id},
    )
    assert denied.status_code == 403

    with Session(auth_client.app.state.test_engine) as db:
        membership = db.query(Membership).filter_by(tenant_id=UUID(tenant_id)).one()
        permission = Permission(code="reports.read", description="Read reports")
        second_tenant = Tenant(name="Other Tenant", slug="other-tenant")
        db.add_all([permission, second_tenant])
        db.flush()
        primary_role = Role(tenant_id=membership.tenant_id, name="report-reader")
        foreign_role = Role(tenant_id=second_tenant.id, name="foreign-report-reader")
        db.add_all([primary_role, foreign_role])
        db.flush()
        db.add(RolePermission(role_id=foreign_role.id, permission_id=permission.id))
        db.commit()
        foreign_tenant_id = str(second_tenant.id)

    foreign_tenant = auth_client.get(
        "/api/v1/test/rbac-probe",
        headers={**auth_headers, "X-Tenant-ID": foreign_tenant_id},
    )
    assert foreign_tenant.status_code == 403

    with Session(auth_client.app.state.test_engine) as db:
        membership = db.query(Membership).filter_by(tenant_id=UUID(tenant_id)).one()
        role = db.query(Role).filter_by(tenant_id=membership.tenant_id, name="report-reader").one()
        permission = db.query(Permission).filter_by(code="reports.read").one()
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        db.add(
            MembershipRole(
                tenant_id=membership.tenant_id,
                membership_id=membership.id,
                role_id=role.id,
            )
        )
        db.commit()

    allowed = auth_client.get(
        "/api/v1/test/rbac-probe",
        headers={**auth_headers, "X-Tenant-ID": tenant_id},
    )
    assert allowed.status_code == 200
    assert allowed.json()["tenant_id"] == tenant_id

    with Session(auth_client.app.state.test_engine) as db:
        membership = db.query(Membership).filter_by(tenant_id=UUID(tenant_id)).one()
        membership.is_active = False
        db.commit()

    inactive_membership = auth_client.get(
        "/api/v1/test/rbac-probe",
        headers={**auth_headers, "X-Tenant-ID": tenant_id},
    )
    assert inactive_membership.status_code == 403

    with Session(auth_client.app.state.test_engine) as db:
        membership = db.query(Membership).filter_by(tenant_id=UUID(tenant_id)).one()
        membership.is_active = True
        tenant = db.query(Tenant).filter_by(id=UUID(tenant_id)).one()
        tenant.is_active = False
        db.commit()

    inactive_tenant = auth_client.get(
        "/api/v1/test/rbac-probe",
        headers={**auth_headers, "X-Tenant-ID": tenant_id},
    )
    assert inactive_tenant.status_code == 403


def test_unauthenticated_state_changes_require_origin(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.test", "password": "incorrect password"},
        headers={"Origin": ""},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Request origin is required"}
