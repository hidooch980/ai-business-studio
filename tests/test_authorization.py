from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.identity.api_dependencies import TenantPrincipal, require_permission
from backend.app.identity.models import (
    Membership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    Tenant,
)
from backend.app.db.session import get_db_session


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

    router = APIRouter()

    @router.get("/rbac-probe")
    def rbac_probe(
        principal: TenantPrincipal = Depends(require_permission("reports.read")),
    ) -> dict:
        return {"tenant_id": str(principal.tenant.id), "membership_id": str(principal.membership.id)}

    auth_client.app.include_router(router, prefix="/api/v1/test")

    denied = auth_client.get(
        "/api/v1/test/rbac-probe",
        headers={"X-Tenant-ID": tenant_id},
    )
    assert denied.status_code == 403

    with Session(auth_client.app.state.test_engine) as db:
        membership = db.query(Membership).filter_by(tenant_id=tenant_id).one()
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
        headers={"X-Tenant-ID": foreign_tenant_id},
    )
    assert foreign_tenant.status_code == 403

    with Session(auth_client.app.state.test_engine) as db:
        membership = db.query(Membership).filter_by(tenant_id=tenant_id).one()
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
        headers={"X-Tenant-ID": tenant_id},
    )
    assert allowed.status_code == 200
    assert allowed.json()["tenant_id"] == tenant_id
