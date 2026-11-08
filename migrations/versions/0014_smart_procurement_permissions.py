"""Add smart procurement permission codes.

Revision ID: 0014_smart_procurement_permissions
Revises: 0013_login_rate_limit_retention
"""
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0014_smart_procurement_permissions"
down_revision = "0013_login_rate_limit_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String(length=120)),
        sa.column("description", sa.String(length=255)),
    )
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String(length=80)),
        sa.column("is_system", sa.Boolean()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
    )
    definitions = {
        "procurement.read": "Preview demand-driven replenishment recommendations",
        "procurement.manage": "Manage supplier and procurement data",
        "procurement.approve": "Approve or reject purchase requests",
    }
    existing = {
        row.code: row.id
        for row in connection.execute(
            sa.select(permissions.c.code, permissions.c.id).where(permissions.c.code.in_(definitions))
        )
    }
    for code, description in definitions.items():
        if code not in existing:
            permission_id = uuid4()
            connection.execute(sa.insert(permissions).values(
                id=permission_id, code=code, description=description
            ))
            existing[code] = permission_id

    owner_ids = connection.execute(
        sa.select(roles.c.id).where(roles.c.name == "owner", roles.c.is_system.is_(True))
    ).scalars().all()
    assignments = {
        (row[0], row[1])
        for row in connection.execute(
            sa.select(role_permissions.c.role_id, role_permissions.c.permission_id).where(
                role_permissions.c.permission_id.in_(list(existing.values()))
            )
        ).all()
    }
    for role_id in owner_ids:
        for permission_id in existing.values():
            if (role_id, permission_id) not in assignments:
                connection.execute(sa.insert(role_permissions).values(
                    role_id=role_id, permission_id=permission_id
                ))


def downgrade() -> None:
    connection = op.get_bind()
    ids = connection.execute(sa.text(
        "SELECT id FROM permissions WHERE code IN "
        "('procurement.read', 'procurement.manage', 'procurement.approve')"
    )).scalars().all()
    if ids:
        connection.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": ids},
        )
    connection.execute(sa.text(
        "DELETE FROM permissions WHERE code IN "
        "('procurement.read', 'procurement.manage', 'procurement.approve')"
    ))
