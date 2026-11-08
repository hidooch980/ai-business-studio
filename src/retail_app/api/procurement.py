"""FastAPI adapters for the procurement-to-payment application services.

The host application must inject an AccessContext resolved from its authenticated
session/membership layer. Tenant and role are never accepted from request bodies.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from retail_app.procurement import chain
from retail_app.procurement.purchase_orders import PurchaseOrder, PurchaseOrderLine
from retail_app.procurement.service import create_purchase_order, create_supplier
from retail_app.procurement.suppliers import Supplier
from retail_app.security.authorization import AccessContext


class SupplierCreateInput(BaseModel):
    id: str
    legal_name: str = Field(min_length=1, max_length=200)
    tax_identifier: str | None = Field(default=None, max_length=64)
    phone: str | None = None
    email: str | None = Field(default=None, max_length=254)
    address: str | None = None


class PurchaseOrderLineInput(BaseModel):
    line_number: int = Field(ge=1)
    item_id: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    quantity_milli: int = Field(gt=0)
    unit_price_minor: int = Field(ge=0)


class PurchaseOrderCreateInput(BaseModel):
    id: str
    branch_id: str
    supplier_id: str
    order_number: str = Field(min_length=1, max_length=64)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    order_date: date
    lines: list[PurchaseOrderLineInput] = Field(min_length=1)


class PurchaseOrderUpdateInput(BaseModel):
    supplier_id: str
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    order_date: date
    lines: list[PurchaseOrderLineInput] = Field(min_length=1)


class ReceiptLineInput(BaseModel):
    po_line_number: int = Field(ge=1)
    received_quantity_milli: int = Field(gt=0)
    accepted_quantity_milli: int = Field(ge=0)
    rejected_quantity_milli: int = Field(ge=0)
    discrepancy_code: str | None = None
    discrepancy_note: str | None = None


class GoodsReceiptInput(BaseModel):
    receipt_number: str = Field(min_length=1, max_length=64)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    lines: list[ReceiptLineInput] = Field(min_length=1)
    allow_overdelivery: bool = False


class SupplierInvoiceLineInput(BaseModel):
    po_line_number: int = Field(ge=1)
    goods_receipt_line_id: str
    quantity_milli: int = Field(gt=0)
    unit_price_minor: int = Field(ge=0)


class SupplierInvoiceMatchInput(BaseModel):
    invoice_id: str
    supplier_id: str
    purchase_order_id: str
    invoice_number: str = Field(min_length=1, max_length=100)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    invoice_date: date
    due_date: date
    invoice_total_minor: int = Field(ge=0)
    lines: list[SupplierInvoiceLineInput] = Field(min_length=1)


class PaymentAllocationInput(BaseModel):
    payable_id: str
    amount_minor: int = Field(gt=0)


class SupplierPaymentInput(BaseModel):
    payment_id: str
    supplier_id: str
    payment_reference: str = Field(min_length=1, max_length=120)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    amount_minor: int = Field(gt=0)
    paid_at: datetime
    method: str
    allocations: list[PaymentAllocationInput] = Field(min_length=1)


def _run(operation: Callable[[], object]) -> object:
    try:
        return operation()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(status_code=409, detail="duplicate business reference") from exc
        raise


def create_procurement_router(database: object, context_dependency: Callable[..., AccessContext]) -> APIRouter:
    """Build routes using an application-provided trusted identity dependency."""
    router = APIRouter(prefix="/api/procurement", tags=["procurement"])

    def request_id(request: Request) -> str:
        return request.headers.get("X-Request-ID", str(uuid4()))

    def idem(value: str | None) -> str:
        if value is None:
            raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
        return value

    @router.post("/suppliers", status_code=201)
    def create_supplier_endpoint(
        body: SupplierCreateInput,
        request: Request,
        context: AccessContext = Depends(context_dependency),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ):
        supplier = Supplier(
            id=body.id, tenant_id=context.tenant_id, legal_name=body.legal_name,
            tax_identifier=body.tax_identifier, phone=body.phone,
            email=body.email, address=body.address,
        )
        return _run(lambda: create_supplier(
            database, context, supplier, idempotency_key=idem(idempotency_key),
            request_id=request_id(request),
        ))

    @router.post("/purchase-orders", status_code=201)
    def create_purchase_order_endpoint(
        body: PurchaseOrderCreateInput,
        request: Request,
        context: AccessContext = Depends(context_dependency),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ):
        order = PurchaseOrder(
            id=body.id, tenant_id=context.tenant_id, branch_id=body.branch_id,
            supplier_id=body.supplier_id, order_number=body.order_number,
            currency=body.currency, order_date=body.order_date,
            lines=tuple(PurchaseOrderLine(**line.model_dump()) for line in body.lines),
        )
        return _run(lambda: create_purchase_order(
            database, context, order, idempotency_key=idem(idempotency_key),
            request_id=request_id(request),
        ))

    @router.get("/purchase-orders")
    def purchase_orders(
        context: AccessContext = Depends(context_dependency),
        branch_id: str | None = None,
        status: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return _run(lambda: chain.list_purchase_orders(
            database, context, branch_id=branch_id, status=status, limit=limit, offset=offset
        ))

    @router.get("/purchase-orders/{order_id}")
    def purchase_order(order_id: str, context: AccessContext = Depends(context_dependency)):
        return _run(lambda: chain.get_purchase_order(database, context, order_id))

    @router.patch("/purchase-orders/{order_id}")
    def update_purchase_order(
        order_id: str,
        body: PurchaseOrderUpdateInput,
        request: Request,
        context: AccessContext = Depends(context_dependency),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ):
        return _run(lambda: chain.update_draft_purchase_order(
            database, context, order_id, supplier_id=body.supplier_id,
            currency=body.currency, order_date=body.order_date,
            lines=[x.model_dump() for x in body.lines],
            idempotency_key=idem(idempotency_key), request_id=request_id(request),
        ))

    @router.post("/purchase-orders/{order_id}/approve")
    def approve_purchase_order(
        order_id: str,
        request: Request,
        context: AccessContext = Depends(context_dependency),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ):
        return _run(lambda: chain.approve_purchase_order(
            database, context, order_id, idempotency_key=idem(idempotency_key),
            request_id=request_id(request),
        ))

    @router.post("/purchase-orders/{order_id}/receipts", status_code=201)
    def post_goods_receipt(
        order_id: str,
        body: GoodsReceiptInput,
        request: Request,
        context: AccessContext = Depends(context_dependency),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ):
        return _run(lambda: chain.receive_goods(
            database, context, order_id, receipt_number=body.receipt_number,
            received_at=body.received_at, lines=[x.model_dump() for x in body.lines],
            allow_overdelivery=body.allow_overdelivery,
            idempotency_key=idem(idempotency_key), request_id=request_id(request),
        ))

    @router.post("/supplier-invoices/match", status_code=201)
    def match_invoice(
        body: SupplierInvoiceMatchInput,
        request: Request,
        context: AccessContext = Depends(context_dependency),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ):
        return _run(lambda: chain.match_supplier_invoice(
            database, context, invoice_id=body.invoice_id, supplier_id=body.supplier_id,
            purchase_order_id=body.purchase_order_id, invoice_number=body.invoice_number,
            currency=body.currency, invoice_date=body.invoice_date, due_date=body.due_date,
            invoice_total_minor=body.invoice_total_minor,
            lines=[x.model_dump() for x in body.lines],
            idempotency_key=idem(idempotency_key), request_id=request_id(request),
        ))

    @router.get("/inventory/stock")
    def inventory_stock(
        context: AccessContext = Depends(context_dependency),
        branch_id: str,
        item_id: str,
    ):
        return _run(lambda: chain.get_stock_balance(
            database, context, branch_id=branch_id, item_id=item_id
        ))

    @router.get("/accounts-payable")
    def accounts_payable(
        context: AccessContext = Depends(context_dependency),
        supplier_id: str | None = None,
        due_before: date | None = None,
        limit: int = Query(100, ge=1, le=200),
    ):
        return _run(lambda: chain.list_accounts_payable(
            database, context, supplier_id=supplier_id, due_before=due_before, limit=limit
        ))

    @router.post("/supplier-payments", status_code=201)
    def post_supplier_payment(
        body: SupplierPaymentInput,
        request: Request,
        context: AccessContext = Depends(context_dependency),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ):
        return _run(lambda: chain.record_supplier_payment(
            database, context, payment_id=body.payment_id, supplier_id=body.supplier_id,
            payment_reference=body.payment_reference, currency=body.currency,
            amount_minor=body.amount_minor, paid_at=body.paid_at, method=body.method,
            allocations=[x.model_dump() for x in body.allocations],
            idempotency_key=idem(idempotency_key), request_id=request_id(request),
        ))

    return router
