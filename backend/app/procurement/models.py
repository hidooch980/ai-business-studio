from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_suppliers_tenant_id_id"),
        UniqueConstraint("tenant_id", "code", name="uq_suppliers_tenant_code"),
        CheckConstraint("length(trim(code)) > 0", name="ck_suppliers_code_nonempty"),
        CheckConstraint("length(trim(name)) > 0", name="ck_suppliers_name_nonempty"),
        Index("ix_suppliers_tenant_active_name", "tenant_id", "is_active", "name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_purchase_orders_tenant_id_id"),
        UniqueConstraint("tenant_id", "order_number", name="uq_purchase_orders_tenant_number"),
        CheckConstraint("status IN ('draft', 'approved', 'partially_received', 'received', 'cancelled')", name="ck_purchase_orders_status"),
        ForeignKeyConstraint(["tenant_id", "supplier_id"], ["suppliers.tenant_id", "suppliers.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "warehouse_id"], ["warehouses.tenant_id", "warehouses.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        Index("ix_purchase_orders_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    supplier_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    order_number: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_purchase_order_lines_tenant_id_id"),
        UniqueConstraint("tenant_id", "purchase_order_id", "product_id", name="uq_purchase_order_lines_order_product"),
        CheckConstraint("quantity_ordered > 0", name="ck_purchase_order_lines_ordered_positive"),
        CheckConstraint("quantity_received >= 0 AND quantity_received <= quantity_ordered", name="ck_purchase_order_lines_received_range"),
        CheckConstraint("quantity_invoiced >= 0 AND quantity_invoiced <= quantity_received", name="ck_purchase_order_lines_invoiced_range"),
        CheckConstraint("unit_cost_minor >= 0", name="ck_purchase_order_lines_cost_nonnegative"),
        ForeignKeyConstraint(["tenant_id", "purchase_order_id"], ["purchase_orders.tenant_id", "purchase_orders.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"], ondelete="RESTRICT"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    quantity_ordered: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity_received: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    quantity_invoiced: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    unit_cost_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ProcurementReceipt(Base):
    __tablename__ = "procurement_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_procurement_receipts_tenant_idempotency"),
        CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_procurement_receipts_idempotency_nonempty"),
        ForeignKeyConstraint(["tenant_id", "purchase_order_id"], ["purchase_orders.tenant_id", "purchase_orders.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        Index("ix_procurement_receipts_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)



class SupplierInvoice(Base):
    __tablename__ = "supplier_invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_supplier_invoices_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "supplier_id",
            "invoice_number",
            name="uq_supplier_invoices_tenant_supplier_number",
        ),
        CheckConstraint(
            "status IN ('matched', 'approved', 'posted', 'partially_paid', 'paid', 'void')",
            name="ck_supplier_invoices_status",
        ),
        CheckConstraint("length(trim(invoice_number)) > 0", name="ck_supplier_invoices_number_nonempty"),
        CheckConstraint("subtotal_minor >= 0", name="ck_supplier_invoices_subtotal_nonnegative"),
        CheckConstraint("tax_minor >= 0", name="ck_supplier_invoices_tax_nonnegative"),
        CheckConstraint("freight_minor >= 0", name="ck_supplier_invoices_freight_nonnegative"),
        CheckConstraint("discount_minor >= 0", name="ck_supplier_invoices_discount_nonnegative"),
        CheckConstraint("total_minor >= 0", name="ck_supplier_invoices_total_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_supplier_invoices_tenant_status_date", "tenant_id", "status", "invoice_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    freight_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    discount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="matched")
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupplierInvoiceLine(Base):
    __tablename__ = "supplier_invoice_lines"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "supplier_invoice_id",
            "purchase_order_line_id",
            name="uq_supplier_invoice_lines_invoice_po_line",
        ),
        CheckConstraint("quantity > 0", name="ck_supplier_invoice_lines_quantity_positive"),
        CheckConstraint("unit_cost_minor >= 0", name="ck_supplier_invoice_lines_cost_nonnegative"),
        CheckConstraint("line_total_minor >= 0", name="ck_supplier_invoice_lines_total_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_id", "supplier_invoice_id"],
            ["supplier_invoices.tenant_id", "supplier_invoices.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_order_line_id"],
            ["purchase_order_lines.tenant_id", "purchase_order_lines.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_supplier_invoice_lines_tenant_invoice", "tenant_id", "supplier_invoice_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_invoice_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    purchase_order_line_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_cost_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
