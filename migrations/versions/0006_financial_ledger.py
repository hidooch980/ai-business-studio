"""Add tenant-scoped double-entry journal ledger.

Revision ID: 0006_financial_ledger
Revises: 0005_tenant_invitations
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_financial_ledger"
down_revision = "0005_tenant_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("debit_total_minor", sa.Integer(), nullable=False),
        sa.Column("credit_total_minor", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "debit_total_minor > 0 AND debit_total_minor = credit_total_minor",
            name="ck_journal_entry_balanced_totals",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_journal_entries_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_journal_entries_tenant_idempotency"),
    )
    op.create_index("ix_journal_entries_tenant_created", "journal_entries", ["tenant_id", "created_at"])
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.String(length=64), nullable=False),
        sa.Column("memo", sa.String(length=255), nullable=True),
        sa.Column("debit_minor", sa.Integer(), nullable=False),
        sa.Column("credit_minor", sa.Integer(), nullable=False),
        sa.CheckConstraint("debit_minor >= 0 AND credit_minor >= 0", name="ck_journal_line_nonnegative"),
        sa.CheckConstraint(
            "(debit_minor > 0 AND credit_minor = 0) OR (credit_minor > 0 AND debit_minor = 0)",
            name="ck_journal_line_one_sided",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "journal_entry_id"],
            ["journal_entries.tenant_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("journal_entry_id", "line_number", name="uq_journal_line_number"),
    )
    op.create_index("ix_journal_lines_tenant_entry", "journal_lines", ["tenant_id", "journal_entry_id"])
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(sa.text("""
            CREATE TRIGGER journal_entries_no_update
            BEFORE UPDATE ON journal_entries
            BEGIN SELECT RAISE(ABORT, 'journal_entries are append-only'); END
        """))
        op.execute(sa.text("""
            CREATE TRIGGER journal_entries_no_delete
            BEFORE DELETE ON journal_entries
            BEGIN SELECT RAISE(ABORT, 'journal_entries are append-only'); END
        """))
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
    elif dialect == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION prevent_journal_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'journal records are append-only'; END;
            $$
        """))
        op.execute(sa.text("""
            CREATE TRIGGER journal_entries_no_update_delete
            BEFORE UPDATE OR DELETE ON journal_entries
            FOR EACH ROW EXECUTE FUNCTION prevent_journal_mutation()
        """))
        op.execute(sa.text("""
            CREATE TRIGGER journal_lines_no_update_delete
            BEFORE UPDATE OR DELETE ON journal_lines
            FOR EACH ROW EXECUTE FUNCTION prevent_journal_mutation()
        """))
        op.execute(sa.text("""
            CREATE FUNCTION prevent_journal_overpost()
            RETURNS trigger LANGUAGE plpgsql AS $
            DECLARE
                target_debit integer;
                target_credit integer;
                posted_debit integer;
                posted_credit integer;
            BEGIN
                SELECT debit_total_minor, credit_total_minor
                  INTO target_debit, target_credit
                  FROM journal_entries
                 WHERE tenant_id = NEW.tenant_id AND id = NEW.journal_entry_id;
                SELECT COALESCE(SUM(debit_minor), 0), COALESCE(SUM(credit_minor), 0)
                  INTO posted_debit, posted_credit
                  FROM journal_lines
                 WHERE tenant_id = NEW.tenant_id AND journal_entry_id = NEW.journal_entry_id;
                IF posted_debit + NEW.debit_minor > target_debit
                   OR posted_credit + NEW.credit_minor > target_credit THEN
                    RAISE EXCEPTION 'journal entry totals cannot be exceeded';
                END IF;
                RETURN NEW;
            END;
            $
        """))
        op.execute(sa.text("""
            CREATE TRIGGER journal_lines_no_overpost
            BEFORE INSERT ON journal_lines
            FOR EACH ROW EXECUTE FUNCTION prevent_journal_overpost()
        """))
    else:
        raise RuntimeError(f"Unsupported database dialect for immutable ledger: {dialect}")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for name in (
            "journal_entries_no_update", "journal_entries_no_delete",
            "journal_lines_no_update", "journal_lines_no_delete", "journal_lines_no_overpost",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {name}"))
    elif dialect == "postgresql":
        op.execute(sa.text("DROP TRIGGER IF EXISTS journal_entries_no_update_delete ON journal_entries"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS journal_lines_no_update_delete ON journal_lines"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS journal_lines_no_overpost ON journal_lines"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_journal_overpost()"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_journal_mutation()"))
    op.drop_index("ix_journal_lines_tenant_entry", table_name="journal_lines")
    op.drop_table("journal_lines")
    op.drop_index("ix_journal_entries_tenant_created", table_name="journal_entries")
    op.drop_table("journal_entries")
