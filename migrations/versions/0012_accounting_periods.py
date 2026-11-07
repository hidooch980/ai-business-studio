"""Add accounting periods and journal posting dates.

Revision ID: 0012_accounting_periods
Revises: 0011_journal_account_links
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_accounting_periods"
down_revision = "0011_journal_account_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_periods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("closed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_date <= end_date", name="ck_financial_period_date_range"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_financial_period_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_financial_period_tenant_name"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_financial_period_tenant_id_id"),
    )
    op.create_index(
        "ix_financial_periods_tenant_dates",
        "financial_periods",
        ["tenant_id", "start_date", "end_date"],
    )
    op.add_column("journal_entries", sa.Column("posting_date", sa.Date(), nullable=True))
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(sa.text("UPDATE journal_entries SET posting_date = created_at::date WHERE posting_date IS NULL"))
    elif dialect == "sqlite":
        op.execute(sa.text("UPDATE journal_entries SET posting_date = date(created_at) WHERE posting_date IS NULL"))
        op.execute(sa.text("""
            CREATE TRIGGER journal_entries_require_open_period
            BEFORE INSERT ON journal_entries
            WHEN NOT EXISTS (
                SELECT 1 FROM financial_periods
                 WHERE tenant_id = NEW.tenant_id
                   AND start_date <= NEW.posting_date
                   AND end_date >= NEW.posting_date
                   AND status = 'open'
            )
            BEGIN SELECT RAISE(ABORT, 'journal posting requires an open accounting period'); END
        """))
    elif dialect == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION enforce_journal_period_open()
            RETURNS trigger LANGUAGE plpgsql AS $period$
            DECLARE period_status text;
            BEGIN
                SELECT status INTO period_status
                  FROM financial_periods
                 WHERE tenant_id = NEW.tenant_id
                   AND start_date <= NEW.posting_date
                   AND end_date >= NEW.posting_date
                 FOR UPDATE;
                IF period_status IS DISTINCT FROM 'open' THEN
                    RAISE EXCEPTION 'journal posting requires an open accounting period';
                END IF;
                RETURN NEW;
            END;
            $period$
        """))
        op.execute(sa.text("""
            CREATE TRIGGER journal_entries_require_open_period
            BEFORE INSERT ON journal_entries
            FOR EACH ROW EXECUTE FUNCTION enforce_journal_period_open()
        """))
    else:
        raise RuntimeError(f"Unsupported database dialect for accounting periods: {dialect}")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(sa.text("DROP TRIGGER IF EXISTS journal_entries_require_open_period"))
    elif dialect == "postgresql":
        op.execute(sa.text("DROP TRIGGER IF EXISTS journal_entries_require_open_period ON journal_entries"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS enforce_journal_period_open()"))
    op.drop_column("journal_entries", "posting_date")
    op.drop_index("ix_financial_periods_tenant_dates", table_name="financial_periods")
    op.drop_table("financial_periods")
