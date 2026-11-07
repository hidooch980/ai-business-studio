from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    memberships: Mapped[list[Membership]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    memberships: Mapped[list[Membership]] = relationship(back_populates="user")


Index("uq_users_email_lower", func.lower(User.email), unique=True)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
        UniqueConstraint("tenant_id", "id", name="uq_membership_tenant_id_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
    roles: Mapped[list[MembershipRole]] = relationship(back_populates="membership")


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
        UniqueConstraint("tenant_id", "id", name="uq_role_tenant_id_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    role_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("permissions.id", ondelete="RESTRICT"), nullable=False, index=True)


class MembershipRole(Base):
    __tablename__ = "membership_roles"
    __table_args__ = (
        UniqueConstraint("membership_id", "role_id", name="uq_membership_role"),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    role_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    membership: Mapped[Membership] = relationship(back_populates="roles")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(160))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class LoginRateLimit(Base):
    __tablename__ = "login_rate_limits"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    identifier_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_journal_entries_tenant_id_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_journal_entries_tenant_idempotency"),
        UniqueConstraint("tenant_id", "reversal_of_id", name="uq_journal_reversal_tenant_original"),
        ForeignKeyConstraint(
            ["tenant_id", "reversal_of_id"],
            ["journal_entries.tenant_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "debit_total_minor > 0 AND debit_total_minor = credit_total_minor",
            name="ck_journal_entry_balanced_totals",
        ),
        Index("ix_journal_entries_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reversal_of_id: Mapped[UUID | None] = mapped_column(Uuid)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    debit_total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    credit_total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "journal_entry_id"],
            ["journal_entries.tenant_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("journal_entry_id", "line_number", name="uq_journal_line_number"),
        CheckConstraint("debit_minor >= 0 AND credit_minor >= 0", name="ck_journal_line_nonnegative"),
        CheckConstraint(
            "(debit_minor > 0 AND credit_minor = 0) OR (credit_minor > 0 AND debit_minor = 0)",
            name="ck_journal_line_one_sided",
        ),
        Index("ix_journal_lines_tenant_entry", "tenant_id", "journal_entry_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    journal_entry_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False)
    financial_account_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    memo: Mapped[str | None] = mapped_column(String(255))
    debit_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_financial_account_tenant_code"),
        UniqueConstraint("tenant_id", "id", name="uq_financial_account_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "parent_account_id"],
            ["financial_accounts.tenant_id", "financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'income', 'expense')",
            name="ck_financial_account_type",
        ),
        CheckConstraint("length(trim(code)) > 0", name="ck_financial_account_code_nonempty"),
        CheckConstraint("length(trim(name)) > 0", name="ck_financial_account_name_nonempty"),
        CheckConstraint(
            "parent_account_id IS NULL OR parent_account_id <> id",
            name="ck_financial_account_not_own_parent",
        ),
        Index("ix_financial_accounts_tenant_type_code", "tenant_id", "account_type", "code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    parent_account_id: Mapped[UUID | None] = mapped_column(Uuid)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class TenantInvitation(Base):
    __tablename__ = "tenant_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_tenant_invitations_tenant_email", "tenant_id", "email"),
        Index("ix_tenant_invitations_expires_at", "expires_at"),
        Index(
            "uq_tenant_invitations_pending_email",
            "tenant_id",
            "email",
            unique=True,
            sqlite_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role_id: Mapped[UUID | None] = mapped_column(Uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
