"""Add tenant-scoped warehouses and append-only inventory movements.

Revision ID: 0008_inventory_ledger
Revises: 0007_product_catalog
Create Date: 2026-11-07
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0008_inventory_ledger"
down_revision = "0007_product_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("uq_products_tenant_id_id", "products", ["tenant_id", "id"], unique=True)

    op.create_table(
        "warehouses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(code)) > 0", name="ck_warehouses_code_nonempty"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_warehouses_name_nonempty"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_warehouses_tenant_id_id"),
    )
    op.create_table(
        "inventory_balances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_on_hand", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity_on_hand >= 0", name="ck_inventory_balance_nonnegative"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "warehouse_id", "product_id",
            name="uq_inventory_balance_tenant_warehouse_product",
        ),
    )
    op.create_index(
        "ix_inventory_balances_tenant_product",
        "inventory_balances",
        ["tenant_id", "product_id"],
    )

    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("quantity_delta", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("reference", sa.String(length=160), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity_delta <> 0", name="ck_inventory_movement_nonzero"),
        sa.CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_inventory_movement_idempotency_nonempty"),
        sa.CheckConstraint(
            "movement_type IN ('receipt', 'issue', 'adjustment')",
            name="ck_inventory_movement_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key",
            name="uq_inventory_movement_tenant_idempotency",
        ),
    )
    op.create_index(
        "ix_inventory_movements_tenant_created",
        "inventory_movements",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_inventory_movements_tenant_stock",
        "inventory_movements",
        ["tenant_id", "warehouse_id", "product_id", "created_at"],
    )

    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(sa.text("""
            CREATE TRIGGER inventory_movements_no_update
            BEFORE UPDATE ON inventory_movements
            BEGIN SELECT RAISE(ABORT, 'inventory_movements are append-only'); END
        """))
        op.execute(sa.text("""
            CREATE TRIGGER inventory_movements_no_delete
            BEFORE DELETE ON inventory_movements
            BEGIN SELECT RAISE(ABORT, 'inventory_movements are append-only'); END
        """))
        op.execute(sa.text("""
            CREATE TRIGGER inventory_movements_apply_balance
            AFTER INSERT ON inventory_movements
            BEGIN
                UPDATE inventory_balances
                   SET quantity_on_hand = quantity_on_hand + NEW.quantity_delta,
                       updated_at = NEW.created_at
                 WHERE tenant_id = NEW.tenant_id
                   AND warehouse_id = NEW.warehouse_id
                   AND product_id = NEW.product_id;
                SELECT CASE WHEN NOT EXISTS (
                    SELECT 1 FROM inventory_balances
                     WHERE tenant_id = NEW.tenant_id
                       AND warehouse_id = NEW.warehouse_id
                       AND product_id = NEW.product_id
                ) THEN RAISE(ABORT, 'inventory balance row is missing') END;
            END
        """))
    elif dialect == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION prevent_inventory_movement_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $inventory$
            BEGIN
                RAISE EXCEPTION 'inventory movements are append-only';
            END;
            $inventory$
        """))
        op.execute(sa.text("""
            CREATE TRIGGER inventory_movements_no_update_delete
            BEFORE UPDATE OR DELETE ON inventory_movements
            FOR EACH ROW EXECUTE FUNCTION prevent_inventory_movement_mutation()
        """))
        op.execute(sa.text("""
            CREATE TRIGGER inventory_movements_no_truncate
            BEFORE TRUNCATE ON inventory_movements
            FOR EACH STATEMENT EXECUTE FUNCTION prevent_inventory_movement_mutation()
        """))
        op.execute(sa.text("""
            CREATE FUNCTION apply_inventory_movement_to_balance()
            RETURNS trigger LANGUAGE plpgsql AS $inventory_balance$
            BEGIN
                UPDATE inventory_balances
                   SET quantity_on_hand = quantity_on_hand + NEW.quantity_delta,
                       updated_at = NEW.created_at
                 WHERE tenant_id = NEW.tenant_id
                   AND warehouse_id = NEW.warehouse_id
                   AND product_id = NEW.product_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'inventory balance row is missing';
                END IF;
                RETURN NEW;
            END;
            $inventory_balance$
        """))
        op.execute(sa.text("""
            CREATE TRIGGER inventory_movements_apply_balance
            AFTER INSERT ON inventory_movements
            FOR EACH ROW EXECUTE FUNCTION apply_inventory_movement_to_balance()
        """))
    else:
        raise RuntimeError(f"Unsupported database dialect for inventory ledger: {dialect}")

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
        "inventory.read": "View tenant warehouses and stock balances",
        "inventory.write": "Manage warehouses and record stock movements",
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
                connection.execute(
                    sa.insert(role_permissions).values(role_id=role_id, permission_id=permission_id)
                )


def downgrade() -> None:
    connection = op.get_bind()
    permission_ids = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code IN ('inventory.read', 'inventory.write')")
    ).scalars().all()
    if permission_ids:
        statement = sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN :ids"
        ).bindparams(sa.bindparam("ids", expanding=True))
        connection.execute(statement, {"ids": permission_ids})
        connection.execute(
            sa.text("DELETE FROM permissions WHERE code IN ('inventory.read', 'inventory.write')")
        )

    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(sa.text("DROP TRIGGER IF EXISTS inventory_movements_no_update"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS inventory_movements_no_delete"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS inventory_movements_apply_balance"))
    elif dialect == "postgresql":
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS inventory_movements_no_update_delete ON inventory_movements"
        ))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS inventory_movements_no_truncate ON inventory_movements"
        ))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS inventory_movements_apply_balance ON inventory_movements"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS apply_inventory_movement_to_balance()"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_inventory_movement_mutation()"))

    op.drop_index("ix_inventory_movements_tenant_stock", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_tenant_created", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_index("ix_inventory_balances_tenant_product", table_name="inventory_balances")
    op.drop_table("inventory_balances")
    op.drop_table("warehouses")
    op.drop_index("uq_products_tenant_id_id", table_name="products")
