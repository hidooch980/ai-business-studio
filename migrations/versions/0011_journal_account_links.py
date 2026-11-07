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


def _restore_sqlite_journal_triggers() -> None:
    op.execute(sa.text("""
        CREATE TRIGGER journal_lines_no_update
        BEFORE UPDATE ON journal_lines
        BEGIN SELECT RAISE(ABORT, 'journal_lines are append-only'); END
    """))
    op.execute(sa.text("""
        CREATE TRIGGER journal_lines_no_delete
        BEFORE DELETE ON journal_lines
        BEGIN SELECT RAISE(ABORT, 'journal_lines are append-only'); END
    """))
    op.execute(sa.text("""
        CREATE TRIGGER journal_lines_no_overpost
        BEFORE INSERT ON journal_lines
        WHEN
            (SELECT COALESCE(SUM(debit_minor), 0) FROM journal_lines
             WHERE journal_entry_id = NEW.journal_entry_id) + NEW.debit_minor
                > (SELECT debit_total_minor FROM journal_entries WHERE id = NEW.journal_entry_id)
            OR
            (SELECT COALESCE(SUM(credit_minor), 0) FROM journal_lines
             WHERE journal_entry_id = NEW.journal_entry_id) + NEW.credit_minor
                > (SELECT credit_total_minor FROM journal_entries WHERE id = NEW.journal_entry_id)
        BEGIN SELECT RAISE(ABORT, 'journal entry totals cannot be exceeded'); END
    """))


def upgrade() -> None:
    with op.batch_alter_table("journal_lines") as batch:
        batch.add_column(sa.Column("financial_account_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_journal_line_tenant_financial_account",
            "financial_accounts",
            ["tenant_id", "financial_account_id"],
            ["tenant_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            "ix_journal_lines_tenant_financial_account",
            ["tenant_id", "financial_account_id"],
        )
    if op.get_bind().dialect.name == "sqlite":
        _restore_sqlite_journal_triggers()


def downgrade() -> None:
    with op.batch_alter_table("journal_lines") as batch:
        batch.drop_index("ix_journal_lines_tenant_financial_account")
        batch.drop_constraint("fk_journal_line_tenant_financial_account", type_="foreignkey")
        batch.drop_column("financial_account_id")
    if op.get_bind().dialect.name == "sqlite":
        _restore_sqlite_journal_triggers()
