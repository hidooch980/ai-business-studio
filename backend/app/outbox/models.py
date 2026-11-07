from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_outbox_tenant_dedupe"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'dead_letter')",
            name="ck_outbox_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_outbox_attempts_nonnegative"),
        CheckConstraint(
            "(status = 'processing' AND locked_until IS NOT NULL AND locked_by IS NOT NULL AND lease_token IS NOT NULL) "
            "OR (status <> 'processing' AND locked_until IS NULL AND locked_by IS NULL AND lease_token IS NULL)",
            name="ck_outbox_lease_state",
        ),
        CheckConstraint(
            "(status = 'delivered' AND delivered_at IS NOT NULL) OR "
            "(status <> 'delivered' AND delivered_at IS NULL)",
            name="ck_outbox_delivery_state",
        ),
        CheckConstraint("length(trim(event_type)) > 0", name="ck_outbox_event_type_nonempty"),
        CheckConstraint("length(trim(aggregate_type)) > 0", name="ck_outbox_aggregate_type_nonempty"),
        CheckConstraint("length(trim(aggregate_id)) > 0", name="ck_outbox_aggregate_id_nonempty"),
        CheckConstraint("length(trim(dedupe_key)) > 0", name="ck_outbox_dedupe_key_nonempty"),
        Index("ix_outbox_ready", "status", "available_at", "created_at"),
        Index("ix_outbox_processing_lease", "status", "locked_until"),
        Index("ix_outbox_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(120))
    lease_token: Mapped[UUID | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
