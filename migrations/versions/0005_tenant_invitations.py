"""Add one-time tenant invitations.

Revision ID: 0005_tenant_invitations
Revises: 0004_audit_append_only
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_tenant_invitations"
down_revision = "0004_audit_append_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_tenant_invitations_tenant_email", "tenant_invitations", ["tenant_id", "email"])
    op.create_index("ix_tenant_invitations_expires_at", "tenant_invitations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_tenant_invitations_expires_at", table_name="tenant_invitations")
    op.drop_index("ix_tenant_invitations_tenant_email", table_name="tenant_invitations")
    op.drop_table("tenant_invitations")
