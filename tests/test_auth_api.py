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
from backend.app.identity.models import Membership, MembershipRole, Permission, Role, RolePermission, Tenant, TenantInvitation, User
from backend.app.identity.security import hash_session_token
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
        permission = db.query(Permission).filter_by(code="reports.read").one()
        second_tenant = Tenant(name="Other Tenant", slug="other-tenant")
        db.add(second_tenant)
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


def test_tenant_owner_can_manage_custom_roles_with_csrf(auth_client: TestClient) -> None:
    payload = {
        "email": "owner-access@example.test",
        "password": "correct horse battery staple",
        "display_name": "Tenant Owner",
        "tenant_name": "Access Studio",
        "tenant_slug": "access-studio",
    }
    registered = auth_client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    tenant_id = registered.json()["memberships"][0]["tenant_id"]
    membership_id = registered.json()["memberships"][0]["id"]
    csrf_token = auth_client.cookies.get("abs_csrf")
    assert csrf_token
    headers = {"X-Tenant-ID": tenant_id, "X-CSRF-Token": csrf_token}

    roles = auth_client.get("/api/v1/access/roles", headers=headers)
    assert roles.status_code == 200
    owner = next(item for item in roles.json()["items"] if item["name"] == "owner")
    assert owner["is_system"] is True
    assert "access.roles.manage" in owner["permission_codes"]

    protected = auth_client.put(
        f"/api/v1/access/roles/{owner['id']}/permissions",
        json={"permission_codes": []},
        headers={"X-Tenant-ID": tenant_id, "X-CSRF-Token": csrf_token},
    )
    assert protected.status_code == 409

    created = auth_client.post(
        "/api/v1/access/roles",
        json={"name": "report-reader", "description": "Read-only reports"},
        headers=headers,
    )
    assert created.status_code == 201
    role_id = created.json()["id"]

    replaced = auth_client.put(
        f"/api/v1/access/roles/{role_id}/permissions",
        json={"permission_codes": ["reports.read"]},
        headers=headers,
    )
    assert replaced.status_code == 200
    assert replaced.json()["permission_codes"] == ["reports.read"]

    assigned = auth_client.put(
        f"/api/v1/access/memberships/{membership_id}/roles/{role_id}",
        headers=headers,
    )
    assert assigned.status_code == 204

    duplicate = auth_client.post(
        "/api/v1/access/roles",
        json={"name": "report-reader"},
        headers=headers,
    )
    assert duplicate.status_code == 409


def test_access_control_mutations_reject_missing_csrf(auth_client: TestClient) -> None:
    payload = {
        "email": "csrf-access@example.test",
        "password": "correct horse battery staple",
        "display_name": "CSRF Owner",
        "tenant_name": "CSRF Studio",
        "tenant_slug": "csrf-studio",
    }
    registered = auth_client.post("/api/v1/auth/register", json=payload)
    tenant_id = registered.json()["memberships"][0]["tenant_id"]
    response = auth_client.post(
        "/api/v1/access/roles",
        json={"name": "unsafe-role"},
        headers={"X-Tenant-ID": tenant_id},
    )
    assert response.status_code == 403



def test_membership_management_lists_members_and_protects_last_owner(auth_client: TestClient) -> None:
    payload = {
        "email": "member-admin@example.test",
        "password": "correct horse battery staple",
        "display_name": "Membership Admin",
        "tenant_name": "Membership Studio",
        "tenant_slug": "membership-studio",
    }
    registered = auth_client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    tenant_id = registered.json()["memberships"][0]["tenant_id"]
    owner_membership_id = registered.json()["memberships"][0]["id"]
    csrf_token = auth_client.cookies.get("abs_csrf")
    assert csrf_token
    headers = {"X-Tenant-ID": tenant_id, "X-CSRF-Token": csrf_token}

    with Session(auth_client.app.state.test_engine) as db:
        member = User(
            email="staff-member@example.test",
            password_hash="not-used-in-this-test",
            display_name="Staff Member",
        )
        db.add(member)
        db.flush()
        staff_membership = Membership(tenant_id=UUID(tenant_id), user_id=member.id)
        db.add(staff_membership)
        db.commit()
        staff_membership_id = str(staff_membership.id)

    listed = auth_client.get("/api/v1/access/memberships", headers={"X-Tenant-ID": tenant_id})
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2
    staff = next(item for item in listed.json()["items"] if item["id"] == staff_membership_id)
    assert staff["email"] == "staff-member@example.test"
    assert staff["is_active"] is True

    self_deactivation = auth_client.patch(
        f"/api/v1/access/memberships/{owner_membership_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert self_deactivation.status_code == 409

    staff_deactivation = auth_client.patch(
        f"/api/v1/access/memberships/{staff_membership_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert staff_deactivation.status_code == 200
    assert staff_deactivation.json()["is_active"] is False

    staff_reactivation = auth_client.patch(
        f"/api/v1/access/memberships/{staff_membership_id}",
        json={"is_active": True},
        headers=headers,
    )
    assert staff_reactivation.status_code == 200
    assert staff_reactivation.json()["is_active"] is True

    roles = auth_client.get("/api/v1/access/roles", headers={"X-Tenant-ID": tenant_id})
    owner_role_id = next(item["id"] for item in roles.json()["items"] if item["name"] == "owner")
    last_owner_removal = auth_client.delete(
        f"/api/v1/access/memberships/{owner_membership_id}/roles/{owner_role_id}",
        headers=headers,
    )
    assert last_owner_removal.status_code == 409

    missing_member = auth_client.patch(
        f"/api/v1/access/memberships/{UUID(int=0)}",
        json={"is_active": False},
        headers=headers,
    )
    assert missing_member.status_code == 404


def test_membership_role_can_be_removed_without_affecting_other_tenants(auth_client: TestClient) -> None:
    payload = {
        "email": "role-remove@example.test",
        "password": "correct horse battery staple",
        "display_name": "Role Remover",
        "tenant_name": "Role Removal Studio",
        "tenant_slug": "role-removal-studio",
    }
    registered = auth_client.post("/api/v1/auth/register", json=payload)
    tenant_id = registered.json()["memberships"][0]["tenant_id"]
    membership_id = registered.json()["memberships"][0]["id"]
    csrf_token = auth_client.cookies.get("abs_csrf")
    headers = {"X-Tenant-ID": tenant_id, "X-CSRF-Token": csrf_token}

    role = auth_client.post(
        "/api/v1/access/roles",
        json={"name": "temporary-reviewer"},
        headers=headers,
    )
    assert role.status_code == 201
    role_id = role.json()["id"]
    updated_role = auth_client.patch(
        f"/api/v1/access/roles/{role_id}",
        json={"name": "temporary-reviewer-v2", "description": "Updated reviewer"},
        headers=headers,
    )
    assert updated_role.status_code == 200
    assert updated_role.json()["name"] == "temporary-reviewer-v2"
    assigned = auth_client.put(
        f"/api/v1/access/memberships/{membership_id}/roles/{role_id}",
        headers=headers,
    )
    assert assigned.status_code == 204

    removed = auth_client.delete(
        f"/api/v1/access/memberships/{membership_id}/roles/{role_id}",
        headers=headers,
    )
    assert removed.status_code == 204

    duplicate_removal = auth_client.delete(
        f"/api/v1/access/memberships/{membership_id}/roles/{role_id}",
        headers=headers,
    )
    assert duplicate_removal.status_code == 404

    deleted_role = auth_client.delete(f"/api/v1/access/roles/{role_id}", headers=headers)
    assert deleted_role.status_code == 204
    missing_role = auth_client.delete(f"/api/v1/access/roles/{role_id}", headers=headers)
    assert missing_role.status_code == 404


def test_invitation_create_accept_is_one_time_and_tenant_scoped(auth_client: TestClient) -> None:
    payload = {
        "email": "invite-owner@example.test",
        "password": "correct horse battery staple",
        "display_name": "Invite Owner",
        "tenant_name": "Invite Studio",
        "tenant_slug": "invite-studio",
    }
    registered = auth_client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    tenant_id = registered.json()["memberships"][0]["tenant_id"]
    csrf_token = auth_client.cookies.get("abs_csrf")
    assert csrf_token
    headers = {"X-Tenant-ID": tenant_id, "X-CSRF-Token": csrf_token}

    system_roles = auth_client.get("/api/v1/access/roles", headers={"X-Tenant-ID": tenant_id})
    owner_role_id = next(item["id"] for item in system_roles.json()["items"] if item["name"] == "owner")
    forbidden_owner_invite = auth_client.post(
        "/api/v1/invitations",
        json={"email": "escalation@example.test", "display_name": "Escalation", "role_id": owner_role_id},
        headers=headers,
    )
    assert forbidden_owner_invite.status_code == 409

    role = auth_client.post(
        "/api/v1/access/roles",
        json={"name": "basic-member", "description": "Basic invited member"},
        headers=headers,
    )
    assert role.status_code == 201
    role_id = role.json()["id"]

    created = auth_client.post(
        "/api/v1/invitations",
        json={"email": " New.Member@Example.test ", "display_name": "New Member", "role_id": role_id},
        headers=headers,
    )
    assert created.status_code == 201
    token = created.json()["invitation_token"]
    assert created.json()["delivery"] == "manual"
    assert created.json()["email"] == "new.member@example.test"

    with Session(auth_client.app.state.test_engine) as db:
        invitation = db.query(TenantInvitation).filter_by(email="new.member@example.test").one()
        assert invitation.token_hash != token
        assert invitation.token_hash == hash_session_token(token)

    accepting_client = TestClient(auth_client.app)
    accepting_client.headers.update({"Origin": str(accepting_client.base_url).rstrip("/")})
    accepted = accepting_client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "password": "a secure invited password", "display_name": "Accepted Member"},
    )
    assert accepted.status_code == 201
    assert accepted.json()["email"] == "new.member@example.test"

    replay = accepting_client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "password": "another secure password"},
    )
    assert replay.status_code == 400

    with Session(auth_client.app.state.test_engine) as db:
        member = db.query(User).filter_by(email="new.member@example.test").one()
        membership = db.query(Membership).filter_by(tenant_id=UUID(tenant_id), user_id=member.id).one()
        assignment = db.query(MembershipRole).filter_by(
            tenant_id=UUID(tenant_id), membership_id=membership.id, role_id=UUID(role_id)
        ).one()
        assert assignment is not None


def test_invitation_resend_rotates_token_and_revoke_invalidates_it(auth_client: TestClient) -> None:
    payload = {
        "email": "invite-admin@example.test",
        "password": "correct horse battery staple",
        "display_name": "Invite Admin",
        "tenant_name": "Invite Lifecycle Studio",
        "tenant_slug": "invite-lifecycle-studio",
    }
    registered = auth_client.post("/api/v1/auth/register", json=payload)
    tenant_id = registered.json()["memberships"][0]["tenant_id"]
    csrf_token = auth_client.cookies.get("abs_csrf")
    headers = {"X-Tenant-ID": tenant_id, "X-CSRF-Token": csrf_token}
    role = auth_client.post("/api/v1/access/roles", json={"name": "invitee"}, headers=headers)
    role_id = role.json()["id"]

    created = auth_client.post(
        "/api/v1/invitations",
        json={"email": "rotate@example.test", "display_name": "Rotate", "role_id": role_id},
        headers=headers,
    )
    invitation_id = created.json()["id"]
    original_token = created.json()["invitation_token"]
    resent = auth_client.post(f"/api/v1/invitations/{invitation_id}/resend", headers=headers)
    assert resent.status_code == 200
    replacement_token = resent.json()["invitation_token"]
    assert replacement_token != original_token

    accepting_client = TestClient(auth_client.app)
    accepting_client.headers.update({"Origin": str(accepting_client.base_url).rstrip("/")})
    old_token = accepting_client.post(
        "/api/v1/invitations/accept",
        json={"token": original_token, "password": "a secure invited password"},
    )
    assert old_token.status_code == 400

    revoked = auth_client.delete(f"/api/v1/invitations/{invitation_id}", headers=headers)
    assert revoked.status_code == 204
    latest_token = accepting_client.post(
        "/api/v1/invitations/accept",
        json={"token": replacement_token, "password": "a secure invited password"},
    )
    assert latest_token.status_code == 400
