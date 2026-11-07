"""Enforce append-only audit event records.

Revision ID: 0004_audit_append_only
Revises: 0003_login_rate_limits
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_audit_append_only"
down_revision = "0003_login_rate_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION prevent_audit_event_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'audit_events are append-only';
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER audit_events_no_update_delete
                BEFORE UPDATE OR DELETE ON audit_events
                FOR EACH ROW
                EXECUTE FUNCTION prevent_audit_event_mutation()
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER audit_events_no_truncate
                BEFORE TRUNCATE ON audit_events
                FOR EACH STATEMENT
                EXECUTE FUNCTION prevent_audit_event_mutation()
                """
            )
        )
    elif dialect == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER audit_events_no_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events are append-only');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER audit_events_no_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events are append-only');
                END
                """
            )
        )
    else:
        raise RuntimeError(f"Append-only audit controls are unsupported for database dialect: {dialect}")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(sa.text("DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_audit_event_mutation()"))
    elif dialect == "sqlite":
        op.execute(sa.text("DROP TRIGGER IF EXISTS audit_events_no_delete"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS audit_events_no_update"))
    else:
        raise RuntimeError(f"Append-only audit controls are unsupported for database dialect: {dialect}")
