"""Add tenant-scoped Moadian connection profiles.

Revision ID: 0019_moadian
Revises: 0018_proc_acct
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_moadian"
down_revision = "0018_proc_acct"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moadian_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tax_memory_uid", sa.String(length=64), nullable=False),
        sa.Column("taxpayer_identifier", sa.String(length=32), nullable=False),
        sa.Column("submission_mode", sa.String(length=12), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=True),
        sa.Column("environment", sa.String(length=12), nullable=False),
        sa.Column("private_key_secret_ref", sa.String(length=200), nullable=True),
        sa.Column("certificate_secret_ref", sa.String(length=200), nullable=True),
        sa.Column("provider_credential_secret_ref", sa.String(length=200), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("submission_mode IN ('direct', 'tsp')", name="ck_moadian_connections_mode"),
        sa.CheckConstraint("environment IN ('sandbox', 'production')", name="ck_moadian_connections_environment"),
        sa.CheckConstraint("submission_mode <> 'tsp' OR provider_code IS NOT NULL", name="ck_moadian_connections_tsp_provider"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_moadian_connections_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "tax_memory_uid", name="uq_moadian_connections_tenant_memory_uid"),
    )
    op.create_index("ix_moadian_connections_tenant_enabled", "moadian_connections", ["tenant_id", "is_enabled"])


def downgrade() -> None:
    op.drop_index("ix_moadian_connections_tenant_enabled", table_name="moadian_connections")
    op.drop_table("moadian_connections")
