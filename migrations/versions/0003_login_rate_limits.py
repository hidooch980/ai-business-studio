"""Add persistent login rate-limit state.

Revision ID: 0003_login_rate_limits
Revises: 0002_session_csrf
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_login_rate_limits"
down_revision = "0002_session_csrf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_rate_limits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identifier_hash"),
    )


def downgrade() -> None:
    op.drop_table("login_rate_limits")
