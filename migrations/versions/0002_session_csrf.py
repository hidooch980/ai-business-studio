"""Add session-bound CSRF token digests.

Revision ID: 0002_session_csrf
Revises: 0001_identity
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_session_csrf"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("csrf_token_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("user_sessions", "csrf_token_hash")
