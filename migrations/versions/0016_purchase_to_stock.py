"""Add suppliers, purchase orders and idempotent receiving.

Revision ID: 0016_purchase_to_stock
Revises: 0015_tenant_module_entitlements
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_purchase_to_stock"
down_revision = "0015_tenant_module_entitlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(code)) > 0", name="ck_suppliers_code_nonempty"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_suppliers_name_nonempty"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_suppliers_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_suppliers_tenant_code"),
    )
    op.create_index("ix_suppliers_tenant_active_name", "suppliers", ["tenant_id", "is_active", "name"])

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.String(48), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'partially_received', 'received', 'cancelled')",
            name="ck_purchase_orders_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "supplier_id"], ["suppliers.tenant_id", "suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "warehouse_id"], ["warehouses.tenant_id", "warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_purchase_orders_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "order_number", name="uq_purchase_orders_tenant_number"),
    )
    op.create_index("ix_purchase_orders_tenant_status_created", "purchase_orders", ["tenant_id", "status", "created_at"])

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_ordered", sa.BigInteger(), nullable=False),
        sa.Column("quantity_received", sa.BigInteger(), nullable=False),
        sa.Column("unit_cost_minor", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity_ordered > 0", name="ck_purchase_order_lines_ordered_positive"),
        sa.CheckConstraint(
            "quantity_received >= 0 AND quantity_received <= quantity_ordered",
            name="ck_purchase_order_lines_received_range",
        ),
        sa.CheckConstraint("unit_cost_minor >= 0", name="ck_purchase_order_lines_cost_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_purchase_order_lines_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "purchase_order_id", "product_id", name="uq_purchase_order_lines_order_product"),
    )

    op.create_table(
        "procurement_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_procurement_receipts_idempotency_nonempty"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_procurement_receipts_tenant_idempotency"),
    )
    op.create_index("ix_procurement_receipts_tenant_created", "procurement_receipts", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_procurement_receipts_tenant_created", table_name="procurement_receipts")
    op.drop_table("procurement_receipts")
    op.drop_table("purchase_order_lines")
    op.drop_index("ix_purchase_orders_tenant_status_created", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_index("ix_suppliers_tenant_active_name", table_name="suppliers")
    op.drop_table("suppliers")
