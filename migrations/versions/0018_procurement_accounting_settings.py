"""Add tenant-scoped procurement accounting mappings.

Revision ID: 0018_procurement_accounting_settings
Revises: 0017_purchase_to_pay
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_procurement_accounting_settings"
down_revision = "0017_purchase_to_pay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procurement_accounting_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_account_code", sa.String(32), nullable=False),
        sa.Column("grni_account_code", sa.String(32), nullable=False),
        sa.Column("ap_account_code", sa.String(32), nullable=False),
        sa.Column("cash_account_code", sa.String(32), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "inventory_account_code <> grni_account_code "
            "AND inventory_account_code <> ap_account_code "
            "AND inventory_account_code <> cash_account_code "
            "AND grni_account_code <> ap_account_code "
            "AND grni_account_code <> cash_account_code "
            "AND ap_account_code <> cash_account_code",
            name="ck_procurement_accounting_settings_distinct_accounts",
        ),
        sa.CheckConstraint("length(base_currency) = 3", name="ck_procurement_accounting_settings_currency"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_procurement_accounting_settings_tenant"),
    )


def downgrade() -> None:
    op.drop_table("procurement_accounting_settings")
