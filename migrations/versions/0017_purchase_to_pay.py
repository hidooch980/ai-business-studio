"""Add supplier invoice matching and accounts payable payments.

Revision ID: 0017_purchase_to_pay
Revises: 0016_purchase_to_stock
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_purchase_to_pay"
down_revision = "0016_purchase_to_stock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(80), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("paid_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'matched', 'approved', 'posted', 'partially_paid', 'paid', 'void')",
            name="ck_supplier_invoices_status",
        ),
        sa.CheckConstraint(
            "total_minor >= 0 AND paid_minor >= 0 AND paid_minor <= total_minor",
            name="ck_supplier_invoice_amounts",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"], ["suppliers.tenant_id", "suppliers.id"], ondelete="RESTRICT"
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
            "tenant_id", "supplier_id", "invoice_number", name="uq_supplier_invoice_vendor_number"
        ),
    )
    op.create_index(
        "ix_supplier_invoices_tenant_status_due",
        "supplier_invoices",
        ["tenant_id", "status", "due_date"],
    )

    op.create_table(
        "supplier_invoice_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("unit_cost_minor", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_supplier_invoice_line_quantity"),
        sa.CheckConstraint("unit_cost_minor >= 0", name="ck_supplier_invoice_line_cost"),
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
            "tenant_id", "supplier_invoice_id", "purchase_order_line_id",
            name="uq_supplier_invoice_line_po_line",
        ),
    )

    op.create_table(
        "supplier_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("payment_reference", sa.String(120), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_supplier_payment_amount_positive"),
        sa.CheckConstraint(
            "length(trim(idempotency_key)) > 0",
            name="ck_supplier_payment_idempotency_nonempty",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_invoice_id"],
            ["supplier_invoices.tenant_id", "supplier_invoices.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_supplier_payment_tenant_idempotency"
        ),
    )
    op.create_index(
        "ix_supplier_payments_tenant_invoice_date",
        "supplier_payments",
        ["tenant_id", "supplier_invoice_id", "payment_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_supplier_payments_tenant_invoice_date", table_name="supplier_payments")
    op.drop_table("supplier_payments")
    op.drop_table("supplier_invoice_lines")
    op.drop_index("ix_supplier_invoices_tenant_status_due", table_name="supplier_invoices")
    op.drop_table("supplier_invoices")
