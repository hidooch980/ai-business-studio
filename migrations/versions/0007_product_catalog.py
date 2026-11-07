"""Add tenant-scoped product catalog.

Revision ID: 0007_product_catalog
Revises: 0006_financial_ledger
Create Date: 2026-11-07
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0007_product_catalog"
down_revision = "0006_financial_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("unit_code", sa.String(length=20), nullable=False),
        sa.Column("barcode", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),
        sa.UniqueConstraint("tenant_id", "barcode", name="uq_products_tenant_barcode"),
    )
    op.create_index(
        "ix_products_tenant_active_name",
        "products",
        ["tenant_id", "is_active", "name"],
    )

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
    codes = {
        "catalog.read": "View tenant product catalog",
        "catalog.write": "Create and update tenant product catalog",
    }
    existing = {
        row.code: row.id
        for row in connection.execute(
            sa.select(permissions.c.code, permissions.c.id).where(permissions.c.code.in_(codes))
        )
    }
    for code, description in codes.items():
        if code not in existing:
            permission_id = uuid4()
            connection.execute(
                sa.insert(permissions).values(id=permission_id, code=code, description=description)
            )
            existing[code] = permission_id

    owner_ids = connection.execute(
        sa.select(roles.c.id).where(roles.c.name == "owner", roles.c.is_system.is_(True))
    ).scalars()
    for role_id in owner_ids:
        for permission_id in existing.values():
            connection.execute(
                sa.insert(role_permissions)
                .values(role_id=role_id, permission_id=permission_id)
                .prefix_with("OR IGNORE")
                if connection.dialect.name == "sqlite"
                else sa.insert(role_permissions).values(role_id=role_id, permission_id=permission_id).on_conflict_do_nothing()
            )


def downgrade() -> None:
    connection = op.get_bind()
    permission_ids = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code IN ('catalog.read', 'catalog.write')")
    ).scalars().all()
    if permission_ids:
        connection.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = ANY(:ids)")
            if connection.dialect.name == "postgresql"
            else sa.text("DELETE FROM role_permissions WHERE permission_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": permission_ids},
        )
        connection.execute(
            sa.text("DELETE FROM permissions WHERE code IN ('catalog.read', 'catalog.write')")
        )
    op.drop_index("ix_products_tenant_active_name", table_name="products")
    op.drop_table("products")
