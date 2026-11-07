from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.identity.authorization import membership_has_permission
from backend.app.identity.models import (
    Membership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
)


def test_permission_is_not_inherited_from_another_membership_in_same_tenant() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="Shared Tenant", slug="shared-tenant")
            first_user = User(
                email="first@example.test",
                password_hash="unused",
                display_name="First",
            )
            second_user = User(
                email="second@example.test",
                password_hash="unused",
                display_name="Second",
            )
            db.add_all([tenant, first_user, second_user])
            db.flush()

            first_membership = Membership(tenant_id=tenant.id, user_id=first_user.id)
            second_membership = Membership(tenant_id=tenant.id, user_id=second_user.id)
            role = Role(tenant_id=tenant.id, name="report-reader")
            permission = Permission(code="reports.read", description="Read reports")
            db.add_all([first_membership, second_membership, role, permission])
            db.flush()

            db.add_all(
                [
                    RolePermission(role_id=role.id, permission_id=permission.id),
                    MembershipRole(
                        tenant_id=tenant.id,
                        membership_id=second_membership.id,
                        role_id=role.id,
                    ),
                ]
            )
            db.commit()

            assert not membership_has_permission(db, first_membership, "reports.read")
            assert membership_has_permission(db, second_membership, "reports.read")
    finally:
        engine.dispose()
