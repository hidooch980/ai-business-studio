"""Add supplier invoice matching and invoiced quantity reservations.

Revision ID: 0017_supplier_invoices
Revises: 0016_purchase_to_stock
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_supplier_invoices"
down_revision = "0016_purchase_to_stock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchase_order_lines",
        sa.Column("quantity_invoiced", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(
        "ck_purchase_order_lines_invoiced_range",
        "purchase_order_lines",
        "quantity_invoiced >= 0 AND quantity_invoiced <= quantity_received",
    )
    op.alter_column("purchase_order_lines", "quantity_invoiced", server_default=None)

    op.create_table(
        "supplier_invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(80), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal_minor", sa.BigInteger(), nullable=False),
        sa.Column("tax_minor", sa.BigInteger(), nullable=False),
        sa.Column("freight_minor", sa.BigInteger(), nullable=False),
        sa.Column("discount_minor", sa.BigInteger(), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('matched', 'approved', 'posted', 'partially_paid', 'paid', 'void')",
            name="ck_supplier_invoices_status",
        ),
        sa.CheckConstraint("length(trim(invoice_number)) > 0", name="ck_supplier_invoices_number_nonempty"),
        sa.CheckConstraint("subtotal_minor >= 0", name="ck_supplier_invoices_subtotal_nonnegative"),
        sa.CheckConstraint("tax_minor >= 0", name="ck_supplier_invoices_tax_nonnegative"),
        sa.CheckConstraint("freight_minor >= 0", name="ck_supplier_invoices_freight_nonnegative"),
        sa.CheckConstraint("discount_minor >= 0", name="ck_supplier_invoices_discount_nonnegative"),
        sa.CheckConstraint("total_minor >= 0", name="ck_supplier_invoices_total_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_supplier_invoices_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "supplier_id",
            "invoice_number",
            name="uq_supplier_invoices_tenant_supplier_number",
        ),
    )
    op.create_index(
        "ix_supplier_invoices_tenant_status_date",
        "supplier_invoices",
        ["tenant_id", "status", "invoice_date"],
    )

    op.create_table(
        "supplier_invoice_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("unit_cost_minor", sa.BigInteger(), nullable=False),
        sa.Column("line_total_minor", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_supplier_invoice_lines_quantity_positive"),
        sa.CheckConstraint("unit_cost_minor >= 0", name="ck_supplier_invoice_lines_cost_nonnegative"),
        sa.CheckConstraint("line_total_minor >= 0", name="ck_supplier_invoice_lines_total_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_invoice_id"],
            ["supplier_invoices.tenant_id", "supplier_invoices.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_line_id"],
            ["purchase_order_lines.tenant_id", "purchase_order_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "supplier_invoice_id",
            "purchase_order_line_id",
            name="uq_supplier_invoice_lines_invoice_po_line",
        ),
    )
    op.create_index(
        "ix_supplier_invoice_lines_tenant_invoice",
        "supplier_invoice_lines",
        ["tenant_id", "supplier_invoice_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_supplier_invoice_lines_tenant_invoice", table_name="supplier_invoice_lines")
    op.drop_table("supplier_invoice_lines")
    op.drop_index("ix_supplier_invoices_tenant_status_date", table_name="supplier_invoices")
    op.drop_table("supplier_invoices")
    op.drop_constraint(
        "ck_purchase_order_lines_invoiced_range",
        "purchase_order_lines",
        type_="check",
    )
    op.drop_column("purchase_order_lines", "quantity_invoiced")
