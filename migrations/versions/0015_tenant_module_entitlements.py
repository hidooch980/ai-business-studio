"""Persist tenant subscriptions and module entitlements.

Revision ID: 0015_tenant_module_entitlements
Revises: 0014_procurement_perms
"""
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0015_tenant_module_entitlements"
down_revision = "0014_smart_procurement_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("edition", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "edition IN ('starter', 'growth', 'business', 'enterprise')",
            name="ck_tenant_subscription_edition",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_tenant_subscription_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_subscription_tenant"),
    )
    op.create_index("ix_tenant_subscriptions_tenant_id", "tenant_subscriptions", ["tenant_id"])
    op.create_table(
        "tenant_module_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("is_entitled", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(module_id)) > 0", name="ck_tenant_module_entitlement_module_id"),
        sa.CheckConstraint("source IN ('edition', 'addon')", name="ck_tenant_module_entitlement_source"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "module_id", name="uq_tenant_module_entitlement"),
    )
    op.create_index(
        "ix_tenant_module_entitlements_tenant_enabled",
        "tenant_module_entitlements",
        ["tenant_id", "is_enabled"],
    )
    op.create_index(
        "ix_tenant_module_entitlements_tenant_id",
        "tenant_module_entitlements",
        ["tenant_id"],
    )

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
        "modules.read": "View tenant module entitlements and subscription",
        "modules.manage": "Change tenant edition and module activation",
    }
    connection = op.get_bind()
    existing = {
        row.code: row.id
        for row in connection.execute(
            sa.select(permissions.c.code, permissions.c.id).where(
                permissions.c.code.in_(definitions)
            )
        )
    }
    for code, description in definitions.items():
        if code not in existing:
            permission_id = uuid4()
            connection.execute(
                sa.insert(permissions).values(
                    id=permission_id, code=code, description=description
                )
            )
            existing[code] = permission_id

    owner_ids = connection.execute(
        sa.select(roles.c.id).where(
            roles.c.name == "owner", roles.c.is_system.is_(True)
        )
    ).scalars().all()
    assignments = {
        (row[0], row[1])
        for row in connection.execute(
            sa.select(role_permissions.c.role_id, role_permissions.c.permission_id)
            .where(role_permissions.c.permission_id.in_(list(existing.values())))
        ).all()
    }
    for role_id in owner_ids:
        for permission_id in existing.values():
            if (role_id, permission_id) not in assignments:
                connection.execute(
                    sa.insert(role_permissions).values(
                        role_id=role_id, permission_id=permission_id
                    )
                )

    tenant_ids = connection.execute(sa.text("SELECT id FROM tenants")).scalars().all()
    for tenant_id in tenant_ids:
        connection.execute(
            sa.text(
                """
                INSERT INTO tenant_subscriptions
                    (id, tenant_id, edition, status, created_at, updated_at)
                VALUES
                    (:id, :tenant_id, 'starter', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ).bindparams(
                sa.bindparam("id", type_=sa.Uuid()),
                sa.bindparam("tenant_id", type_=sa.Uuid()),
            ).params(id=uuid4(), tenant_id=tenant_id)
        )
        for module_id in ("platform", "catalog", "inventory", "finance", "reports"):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO tenant_module_entitlements
                        (id, tenant_id, module_id, source, is_entitled, is_enabled,
                         created_at, updated_at)
                    VALUES
                        (:id, :tenant_id, :module_id, 'edition', TRUE, TRUE,
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ).bindparams(
                    sa.bindparam("id", type_=sa.Uuid()),
                    sa.bindparam("tenant_id", type_=sa.Uuid()),
                ).params(id=uuid4(), tenant_id=tenant_id, module_id=module_id)
            )


def downgrade() -> None:
    connection = op.get_bind()
    permission_ids = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code IN ('modules.read', 'modules.manage')")
    ).scalars().all()
    if permission_ids:
        connection.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": permission_ids},
        )
    connection.execute(
        sa.text("DELETE FROM permissions WHERE code IN ('modules.read', 'modules.manage')")
    )
    op.drop_index("ix_tenant_module_entitlements_tenant_id", table_name="tenant_module_entitlements")
    op.drop_index(
        "ix_tenant_module_entitlements_tenant_enabled",
        table_name="tenant_module_entitlements",
    )
    op.drop_table("tenant_module_entitlements")
    op.drop_index("ix_tenant_subscriptions_tenant_id", table_name="tenant_subscriptions")
    op.drop_table("tenant_subscriptions")
