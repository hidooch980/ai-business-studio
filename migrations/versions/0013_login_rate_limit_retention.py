"""Index login throttle records for bounded retention cleanup.

Revision ID: 0013_login_rate_limit_retention
Revises: 0012_accounting_periods
Create Date: 2026-11-07
"""

from alembic import op

revision = "0013_login_rate_limit_retention"
down_revision = "0012_accounting_periods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_login_rate_limits_updated_at",
        "login_rate_limits",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_login_rate_limits_updated_at", table_name="login_rate_limits")
