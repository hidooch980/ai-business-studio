"""Add tenant-scoped chart of accounts.

Revision ID: 0009_financial_accounts
Revises: 0008_inventory_ledger
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_financial_accounts"
down_revision = "0008_inventory_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("account_type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("parent_account_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'income', 'expense')",
            name="ck_financial_account_type",
        ),
        sa.CheckConstraint("length(trim(code)) > 0", name="ck_financial_account_code_nonempty"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_financial_account_name_nonempty"),
        sa.CheckConstraint(
            "parent_account_id IS NULL OR parent_account_id <> id",
            name="ck_financial_account_not_own_parent",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_account_id"],
            ["financial_accounts.tenant_id", "financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_financial_account_tenant_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_financial_account_tenant_id_id"),
    )
    op.create_index(
        "ix_financial_accounts_tenant_type_code",
        "financial_accounts",
        ["tenant_id", "account_type", "code"],
    )


def downgrade() -> None:
    op.drop_index("ix_financial_accounts_tenant_type_code", table_name="financial_accounts")
    op.drop_table("financial_accounts")
