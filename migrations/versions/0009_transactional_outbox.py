"""Add durable transactional outbox.

Revision ID: 0010_transactional_outbox
Revises: 0009_financial_accounts
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_transactional_outbox"
down_revision = "0009_financial_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=80), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'dead_letter')",
            name="ck_outbox_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_outbox_attempts_nonnegative"),
        sa.CheckConstraint(
            "(status = 'processing' AND locked_until IS NOT NULL AND locked_by IS NOT NULL AND lease_token IS NOT NULL) "
            "OR (status <> 'processing' AND locked_until IS NULL AND locked_by IS NULL AND lease_token IS NULL)",
            name="ck_outbox_lease_state",
        ),
        sa.CheckConstraint(
            "(status = 'delivered' AND delivered_at IS NOT NULL) OR "
            "(status <> 'delivered' AND delivered_at IS NULL)",
            name="ck_outbox_delivery_state",
        ),
        sa.CheckConstraint("length(trim(event_type)) > 0", name="ck_outbox_event_type_nonempty"),
        sa.CheckConstraint("length(trim(aggregate_type)) > 0", name="ck_outbox_aggregate_type_nonempty"),
        sa.CheckConstraint("length(trim(aggregate_id)) > 0", name="ck_outbox_aggregate_id_nonempty"),
        sa.CheckConstraint("length(trim(dedupe_key)) > 0", name="ck_outbox_dedupe_key_nonempty"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_outbox_tenant_dedupe"),
    )
    op.create_index("ix_outbox_ready", "outbox_events", ["status", "available_at", "created_at"])
    op.create_index("ix_outbox_tenant_created", "outbox_events", ["tenant_id", "created_at"])
    op.create_index("ix_outbox_processing_lease", "outbox_events", ["status", "locked_until"])


def downgrade() -> None:
    op.drop_index("ix_outbox_processing_lease", table_name="outbox_events")
    op.drop_index("ix_outbox_tenant_created", table_name="outbox_events")
    op.drop_index("ix_outbox_ready", table_name="outbox_events")
    op.drop_table("outbox_events")
