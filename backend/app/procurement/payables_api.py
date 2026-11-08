import hashlib
import json
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.finance.ledger import AccountingPeriodConflictError, JournalConflictError, create_journal_entry
from backend.app.identity.api_dependencies import (
    TenantPrincipal,
    require_csrf_protection,
    require_module,
    require_permission,
)
from backend.app.identity.models import AuditEvent, JournalEntry
from backend.app.procurement.models import (
    ProcurementAccountingSettings,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierInvoice,
    SupplierInvoiceLine,
    SupplierPayment,
)

router = APIRouter(prefix="/procurement/payables", tags=["purchase-to-pay"])

InvoiceNumber = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Currency = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=3)]
PaymentReference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class SupplierInvoiceLineInput(BaseModel):
    purchase_order_line_id: UUID
    quantity: int = Field(gt=0, le=2_000_000_000)
    unit_cost_minor: int = Field(ge=0, le=9_000_000_000_000)


class SupplierInvoiceCreateRequest(BaseModel):
    supplier_id: UUID
    purchase_order_id: UUID
    invoice_number: InvoiceNumber
    invoice_date: date
    due_date: date
    currency: Currency = "USD"
    lines: list[SupplierInvoiceLineInput] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_dates_and_lines(self) -> "SupplierInvoiceCreateRequest":
        if self.due_date < self.invoice_date:
            raise ValueError("Invoice due date cannot precede invoice date")
        ids = [line.purchase_order_line_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each purchase order line may appear only once")
        if not self.currency.isascii() or not self.currency.isalpha():
            raise ValueError("Currency must be a three-letter code")
        return self


class SupplierPaymentRequest(BaseModel):
    amount_minor: int = Field(gt=0, le=9_000_000_000_000)
    currency: Currency
    payment_date: date
    payment_reference: PaymentReference


def _audit(db: Session, principal: TenantPrincipal, action: str, kind: str, resource_id: UUID) -> None:
    db.add(AuditEvent(
        tenant_id=principal.tenant.id,
        actor_user_id=principal.user.id,
        action=action,
        resource_type=kind,
        resource_id=str(resource_id),
        outcome="success",
    ))


def _invoice_dict(db: Session, invoice: SupplierInvoice) -> dict:
    lines = db.scalars(
        select(SupplierInvoiceLine).where(
            SupplierInvoiceLine.tenant_id == invoice.tenant_id,
            SupplierInvoiceLine.supplier_invoice_id == invoice.id,
        ).order_by(SupplierInvoiceLine.id)
    ).all()
    return {
        "id": str(invoice.id),
        "supplier_id": str(invoice.supplier_id),
        "purchase_order_id": str(invoice.purchase_order_id),
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "currency": invoice.currency,
        "total_minor": invoice.total_minor,
        "paid_minor": invoice.paid_minor,
        "outstanding_minor": invoice.total_minor - invoice.paid_minor,
        "status": invoice.status,
        "lines": [{
            "id": str(line.id),
            "purchase_order_line_id": str(line.purchase_order_line_id),
            "quantity": line.quantity,
            "unit_cost_minor": line.unit_cost_minor,
        } for line in lines],
    }


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
def create_supplier_invoice(
    payload: SupplierInvoiceCreateRequest,
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    supplier = db.scalar(select(Supplier).where(
        Supplier.id == payload.supplier_id,
        Supplier.tenant_id == principal.tenant.id,
        Supplier.is_active.is_(True),
    ))
    order = db.scalar(select(PurchaseOrder).where(
        PurchaseOrder.id == payload.purchase_order_id,
        PurchaseOrder.tenant_id == principal.tenant.id,
    ))
    if supplier is None or order is None:
        raise HTTPException(status_code=404, detail="Supplier or purchase order not found in this tenant")
    if order.supplier_id != supplier.id:
        raise HTTPException(status_code=409, detail="Invoice supplier does not match purchase order supplier")
    invoice_id = uuid4()
    invoice = SupplierInvoice(
        id=invoice_id,
        tenant_id=principal.tenant.id,
        supplier_id=supplier.id,
        purchase_order_id=order.id,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        currency=payload.currency.upper(),
        total_minor=0,
        paid_minor=0,
        status="draft",
        created_by_user_id=principal.user.id,
    )
    lines = [
        SupplierInvoiceLine(
            tenant_id=principal.tenant.id,
            supplier_invoice_id=invoice_id,
            purchase_order_line_id=item.purchase_order_line_id,
            quantity=item.quantity,
            unit_cost_minor=item.unit_cost_minor,
        )
        for item in payload.lines
    ]
    db.add(invoice)
    db.add_all(lines)
    try:
        db.flush()
        _audit(db, principal, "procurement.supplier_invoice_created", "supplier_invoice", invoice.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Invoice number or invoice lines conflict with existing records") from exc
    db.refresh(invoice)
    return _invoice_dict(db, invoice)


@router.post("/invoices/{invoice_id}/match")
def match_supplier_invoice(
    invoice_id: UUID,
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    invoice = db.scalar(select(SupplierInvoice).where(
        SupplierInvoice.id == invoice_id,
        SupplierInvoice.tenant_id == principal.tenant.id,
    ).with_for_update())
    if invoice is None:
        raise HTTPException(status_code=404, detail="Supplier invoice not found")
    if invoice.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft invoices can be matched")
    order = db.scalar(select(PurchaseOrder).where(
        PurchaseOrder.id == invoice.purchase_order_id,
        PurchaseOrder.tenant_id == principal.tenant.id,
    ).with_for_update())
    if order is None or order.supplier_id != invoice.supplier_id:
        raise HTTPException(status_code=409, detail="Purchase order and supplier no longer match")
    accounting = db.scalar(select(ProcurementAccountingSettings).where(
        ProcurementAccountingSettings.tenant_id == principal.tenant.id
    ))
    if accounting is None:
        raise HTTPException(status_code=409, detail="Procurement accounting settings must be configured before invoice matching")
    if invoice.currency != accounting.base_currency:
        raise HTTPException(status_code=409, detail="Invoice currency must match the configured procurement base currency")
    lines = db.scalars(select(SupplierInvoiceLine).where(
        SupplierInvoiceLine.tenant_id == principal.tenant.id,
        SupplierInvoiceLine.supplier_invoice_id == invoice.id,
    ).with_for_update()).all()
    total = 0
    for invoice_line in lines:
        po_line = db.scalar(select(PurchaseOrderLine).where(
            PurchaseOrderLine.id == invoice_line.purchase_order_line_id,
            PurchaseOrderLine.tenant_id == principal.tenant.id,
            PurchaseOrderLine.purchase_order_id == order.id,
        ).with_for_update())
        if po_line is None:
            raise HTTPException(status_code=404, detail="Purchase order line not found")
        previously_invoiced = db.scalar(
            select(func.coalesce(func.sum(SupplierInvoiceLine.quantity), 0))
            .join(SupplierInvoice, SupplierInvoice.id == SupplierInvoiceLine.supplier_invoice_id)
            .where(
                SupplierInvoiceLine.tenant_id == principal.tenant.id,
                SupplierInvoiceLine.purchase_order_line_id == po_line.id,
                SupplierInvoice.id != invoice.id,
                SupplierInvoice.status.in_(["matched", "approved", "posted", "partially_paid", "paid"]),
            )
        ) or 0
        if invoice_line.quantity + previously_invoiced > po_line.quantity_received:
            raise HTTPException(status_code=409, detail="Invoice quantity exceeds goods received quantity")
        if invoice_line.unit_cost_minor != po_line.unit_cost_minor:
            raise HTTPException(status_code=409, detail="Invoice unit price does not match approved purchase order")
        total += invoice_line.quantity * invoice_line.unit_cost_minor
    invoice.total_minor = total
    invoice.status = "matched"
    invoice.updated_at = datetime.now(UTC)
    _audit(db, principal, "procurement.supplier_invoice_matched", "supplier_invoice", invoice.id)
    db.commit()
    db.refresh(invoice)
    return _invoice_dict(db, invoice)


@router.post("/invoices/{invoice_id}/approve")
def approve_supplier_invoice(
    invoice_id: UUID,
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.approve")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    invoice = db.scalar(select(SupplierInvoice).where(
        SupplierInvoice.id == invoice_id,
        SupplierInvoice.tenant_id == principal.tenant.id,
    ).with_for_update())
    if invoice is None:
        raise HTTPException(status_code=404, detail="Supplier invoice not found")
    if invoice.status != "matched":
        raise HTTPException(status_code=409, detail="Only matched invoices can be approved")
    invoice.status = "approved"
    invoice.approved_by_user_id = principal.user.id
    invoice.approved_at = datetime.now(UTC)
    invoice.updated_at = datetime.now(UTC)
    _audit(db, principal, "procurement.supplier_invoice_approved", "supplier_invoice", invoice.id)
    db.commit()
    db.refresh(invoice)
    return _invoice_dict(db, invoice)


@router.post("/invoices/{invoice_id}/post")
def post_supplier_invoice(
    invoice_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    invoice = db.scalar(select(SupplierInvoice).where(
        SupplierInvoice.id == invoice_id,
        SupplierInvoice.tenant_id == principal.tenant.id,
    ).with_for_update())
    if invoice is None:
        raise HTTPException(status_code=404, detail="Supplier invoice not found")
    journal_key = f"procurement-invoice:{invoice.id}"
    if invoice.status == "posted":
        journal = db.scalar(select(JournalEntry).where(
            JournalEntry.tenant_id == principal.tenant.id,
            JournalEntry.idempotency_key == journal_key,
        ))
        return {**_invoice_dict(db, invoice), "journal_entry_id": str(journal.id) if journal else None, "replayed": True}
    if invoice.status != "approved":
        raise HTTPException(status_code=409, detail="Only approved invoices can be posted to accounts payable")
    accounting = db.scalar(select(ProcurementAccountingSettings).where(
        ProcurementAccountingSettings.tenant_id == principal.tenant.id
    ))
    if accounting is None:
        raise HTTPException(status_code=409, detail="Procurement accounting settings are not configured")
    if invoice.currency != accounting.base_currency:
        raise HTTPException(status_code=409, detail="Invoice currency does not match procurement accounting base currency")
    if invoice.total_minor <= 0 or invoice.total_minor > 2_147_483_647:
        raise HTTPException(status_code=409, detail="Invoice total must be positive and within the general-ledger limit")
    invoice.status = "posted"
    invoice.updated_at = datetime.now(UTC)
    try:
        journal, _ = create_journal_entry(
            db,
            tenant_id=principal.tenant.id,
            actor_user_id=principal.user.id,
            idempotency_key=journal_key,
            currency=invoice.currency,
            description=f"Supplier invoice {invoice.invoice_number} posted to accounts payable"[:500],
            posting_date=invoice.invoice_date,
            lines=[
                {"account_code": accounting.grni_account_code, "memo": "Clear goods received not invoiced", "debit_minor": invoice.total_minor, "credit_minor": 0},
                {"account_code": accounting.ap_account_code, "memo": "Supplier accounts payable", "debit_minor": 0, "credit_minor": invoice.total_minor},
            ],
            commit=False,
        )
        _audit(db, principal, "finance.accounts_payable_posted", "supplier_invoice", invoice.id)
        db.commit()
        db.refresh(invoice)
    except (AccountingPeriodConflictError, JournalConflictError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {**_invoice_dict(db, invoice), "journal_entry_id": str(journal.id), "replayed": False}


@router.post("/invoices/{invoice_id}/payments", status_code=status.HTTP_201_CREATED)
def record_supplier_payment(
    invoice_id: UUID,
    payload: SupplierPaymentRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="Idempotency-Key cannot be blank")
    normalized = {
        "invoice_id": str(invoice_id),
        "amount_minor": payload.amount_minor,
        "currency": payload.currency.upper(),
        "payment_date": payload.payment_date.isoformat(),
        "payment_reference": payload.payment_reference,
    }
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = db.scalar(select(SupplierPayment).where(
        SupplierPayment.tenant_id == principal.tenant.id,
        SupplierPayment.idempotency_key == key,
    ))
    if existing is not None:
        if existing.request_hash != digest:
            raise HTTPException(status_code=409, detail="Idempotency-Key was used for another payment")
        journal = db.scalar(select(JournalEntry).where(
            JournalEntry.tenant_id == principal.tenant.id,
            JournalEntry.idempotency_key == f"supplier-payment:{existing.id}",
        ))
        return {
            "payment_id": str(existing.id),
            "invoice_id": str(existing.supplier_invoice_id),
            "journal_entry_id": str(journal.id) if journal else None,
            "replayed": True,
        }
    invoice = db.scalar(select(SupplierInvoice).where(
        SupplierInvoice.id == invoice_id,
        SupplierInvoice.tenant_id == principal.tenant.id,
    ).with_for_update())
    if invoice is None:
        raise HTTPException(status_code=404, detail="Supplier invoice not found")
    if invoice.status not in {"posted", "partially_paid"}:
        raise HTTPException(status_code=409, detail="Invoice must be posted to accounts payable before payment")
    accounting = db.scalar(select(ProcurementAccountingSettings).where(
        ProcurementAccountingSettings.tenant_id == principal.tenant.id
    ))
    if accounting is None:
        raise HTTPException(status_code=409, detail="Procurement accounting settings are not configured")
    if payload.currency.upper() != invoice.currency or invoice.currency != accounting.base_currency:
        raise HTTPException(status_code=409, detail="Payment currency must match invoice and configured base currency")
    if payload.amount_minor > invoice.total_minor - invoice.paid_minor:
        raise HTTPException(status_code=409, detail="Payment exceeds outstanding invoice balance")
    payment_id = uuid4()
    payment = SupplierPayment(
        id=payment_id,
        tenant_id=principal.tenant.id,
        supplier_invoice_id=invoice.id,
        idempotency_key=key,
        request_hash=digest,
        payment_reference=payload.payment_reference,
        amount_minor=payload.amount_minor,
        currency=payload.currency.upper(),
        payment_date=payload.payment_date,
        created_by_user_id=principal.user.id,
    )
    db.add(payment)
    invoice.paid_minor += payload.amount_minor
    invoice.status = "paid" if invoice.paid_minor == invoice.total_minor else "partially_paid"
    invoice.updated_at = datetime.now(UTC)
    journal_key = f"supplier-payment:{payment_id}"
    try:
        db.flush()
        journal, _ = create_journal_entry(
            db,
            tenant_id=principal.tenant.id,
            actor_user_id=principal.user.id,
            idempotency_key=journal_key,
            currency=invoice.currency,
            description=f"Supplier payment {payload.payment_reference}"[:500],
            posting_date=payload.payment_date,
            lines=[
                {"account_code": accounting.ap_account_code, "memo": "Settle supplier payable", "debit_minor": payload.amount_minor, "credit_minor": 0},
                {"account_code": accounting.cash_account_code, "memo": "Cash or bank payment recorded", "debit_minor": 0, "credit_minor": payload.amount_minor},
            ],
            commit=False,
        )
        _audit(db, principal, "finance.supplier_payment_recorded", "supplier_payment", payment.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = db.scalar(select(SupplierPayment).where(
            SupplierPayment.tenant_id == principal.tenant.id,
            SupplierPayment.idempotency_key == key,
        ))
        if raced is not None and raced.request_hash == digest:
            saved_journal = db.scalar(select(JournalEntry).where(
                JournalEntry.tenant_id == principal.tenant.id,
                JournalEntry.idempotency_key == f"supplier-payment:{raced.id}",
            ))
            return {
                "payment_id": str(raced.id),
                "invoice_id": str(raced.supplier_invoice_id),
                "journal_entry_id": str(saved_journal.id) if saved_journal else None,
                "replayed": True,
            }
        raise HTTPException(status_code=409, detail="Payment conflicts with another request") from exc
    except (AccountingPeriodConflictError, JournalConflictError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "payment_id": str(payment.id),
        "invoice_id": str(invoice.id),
        "amount_minor": payment.amount_minor,
        "outstanding_minor": invoice.total_minor - invoice.paid_minor,
        "status": invoice.status,
        "journal_entry_id": str(journal.id),
        "replayed": False,
    }


@router.get("/invoices")
def list_supplier_invoices(
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.read")),
    db: Session = Depends(get_db_session),
    invoice_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(SupplierInvoice).where(SupplierInvoice.tenant_id == principal.tenant.id)
    if invoice_status is not None:
        statement = statement.where(SupplierInvoice.status == invoice_status)
    items = db.scalars(statement.order_by(SupplierInvoice.due_date, SupplierInvoice.id).offset(offset).limit(limit)).all()
    return {"items": [_invoice_dict(db, item) for item in items], "limit": limit, "offset": offset}
