"""Link posted journal lines to tenant-owned chart accounts.

Revision ID: 0011_journal_account_links
Revises: 0010_transactional_outbox
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_journal_account_links"
down_revision = "0010_transactional_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("journal_lines", sa.Column("financial_account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_journal_line_tenant_financial_account",
        "journal_lines",
        "financial_accounts",
        ["tenant_id", "financial_account_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_journal_lines_tenant_financial_account",
        "journal_lines",
        ["tenant_id", "financial_account_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_journal_lines_tenant_financial_account", table_name="journal_lines")
    op.drop_constraint("fk_journal_line_tenant_financial_account", "journal_lines", type_="foreignkey")
    op.drop_column("journal_lines", "financial_account_id")
