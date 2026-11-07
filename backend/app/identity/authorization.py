from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.identity.models import (
    Membership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)


def membership_has_permission(db: Session, membership: Membership, permission_code: str) -> bool:
    statement = (
        select(Permission.id)
        .select_from(MembershipRole)
        .join(
            Role,
            (Role.id == MembershipRole.role_id)
            & (Role.tenant_id == MembershipRole.tenant_id),
        )
        .join(
            RolePermission,
            RolePermission.role_id == Role.id,
        )
        .join(
            Permission,
            Permission.id == RolePermission.permission_id,
        )
        .where(
            MembershipRole.tenant_id == membership.tenant_id,
            MembershipRole.membership_id == membership.id,
            Role.tenant_id == membership.tenant_id,
            Permission.code == permission_code,
            membership.is_active.is_(True),
        )
        .limit(1)
    )
    return db.scalar(statement) is not None
