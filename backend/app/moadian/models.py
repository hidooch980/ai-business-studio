from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class MoadianConnection(Base):
    """Tenant-scoped Moadian memory profile; credentials live in a secret manager."""

    __tablename__ = "moadian_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_moadian_connections_tenant_id_id"),
        UniqueConstraint("tenant_id", "tax_memory_uid", name="uq_moadian_connections_tenant_memory_uid"),
        CheckConstraint("submission_mode IN ('direct', 'tsp')", name="ck_moadian_connections_mode"),
        CheckConstraint("environment IN ('sandbox', 'production')", name="ck_moadian_connections_environment"),
        CheckConstraint(
            "submission_mode <> 'tsp' OR provider_code IS NOT NULL",
            name="ck_moadian_connections_tsp_provider",
        ),
        Index("ix_moadian_connections_tenant_enabled", "tenant_id", "is_enabled"),
        ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    tax_memory_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    taxpayer_identifier: Mapped[str] = mapped_column(String(32), nullable=False)
    submission_mode: Mapped[str] = mapped_column(String(12), nullable=False)
    provider_code: Mapped[str | None] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(12), nullable=False, default="sandbox")
    private_key_secret_ref: Mapped[str | None] = mapped_column(String(200))
    certificate_secret_ref: Mapped[str | None] = mapped_column(String(200))
    provider_credential_secret_ref: Mapped[str | None] = mapped_column(String(200))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
