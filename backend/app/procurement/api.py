import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.catalog.models import Product
from backend.app.db.session import get_db_session
from backend.app.finance.ledger import AccountingPeriodConflictError, JournalConflictError, create_journal_entry
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_module
from backend.app.identity.models import AuditEvent
from backend.app.inventory.models import InventoryBalance, InventoryMovement, Warehouse
from backend.app.outbox.service import enqueue_outbox_event
from backend.app.procurement.engine import (
    DemandPoint,
    ReplenishmentInput,
    SupplierQuote,
    calculate_replenishment,
    rank_supplier_quotes,
    transferable_quantity,
)
from backend.app.procurement.models import (
    ProcurementAccountingSettings,
    ProcurementReceipt,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)

router = APIRouter(prefix="/procurement", tags=["smart-procurement"])
Positive = Annotated[Decimal, Field(ge=0)]
StrictlyPositive = Annotated[Decimal, Field(gt=0)]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
SupplierCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
SupplierName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]


class DemandPointInput(BaseModel):
    units: Positive
    stockout_censored: bool = False
    promotion: bool = False


class SupplierQuoteInput(BaseModel):
    supplier_id: NonEmpty
    unit_cost_minor: int = Field(ge=0)
    freight_per_unit_minor: int = Field(default=0, ge=0)
    lead_time_days: int = Field(default=1, ge=0, le=365)
    lead_time_std_days: Positive = Decimal("0")
    on_time_rate: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    quality_acceptance_rate: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    payment_terms_days: int = Field(default=0, ge=0, le=3650)
    capacity_units: Positive | None = None
    approved: bool = True


class SourceBranchInput(BaseModel):
    branch_id: NonEmpty
    sellable_units: Positive
    reserved_units: Positive = Decimal("0")
    safety_stock_units: Positive = Decimal("0")


class ProcurementPreviewRequest(BaseModel):
    product_id: UUID
    warehouse_id: UUID
    demand_history: list[DemandPointInput] = Field(min_length=1, max_length=365)
    sellable_on_hand: Positive
    reserved_units: Positive = Decimal("0")
    confirmed_inbound: Positive = Decimal("0")
    backordered_units: Positive = Decimal("0")
    lead_time_days: int = Field(ge=0, le=365)
    review_period_days: int = Field(default=7, ge=0, le=365)
    service_level: Decimal = Field(default=Decimal("0.95"), gt=0, lt=1)
    minimum_order_quantity: StrictlyPositive = Decimal("1")
    order_multiple: StrictlyPositive = Decimal("1")
    shelf_life_days: int | None = Field(default=None, gt=0, le=36500)
    storage_capacity_units: Positive | None = None
    budget_minor: int | None = Field(default=None, ge=0)
    suppliers: list[SupplierQuoteInput] = Field(default_factory=list, max_length=100)
    source_branches: list[SourceBranchInput] = Field(default_factory=list, max_length=100)


class SupplierCreateRequest(BaseModel):
    code: SupplierCode
    name: SupplierName
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=320)] | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    payment_terms_days: int = Field(default=0, ge=0, le=3650)


class PurchaseOrderLineInput(BaseModel):
    product_id: UUID
    quantity: int = Field(gt=0, le=2_000_000_000)
    unit_cost_minor: int = Field(ge=0, le=9_000_000_000_000)


class PurchaseOrderCreateRequest(BaseModel):
    supplier_id: UUID
    warehouse_id: UUID
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    lines: list[PurchaseOrderLineInput] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_products(self) -> "PurchaseOrderCreateRequest":
        product_ids = [line.product_id for line in self.lines]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Each product may appear only once in a purchase order")
        return self


class ReceiptLineInput(BaseModel):
    purchase_order_line_id: UUID
    quantity: int = Field(gt=0, le=2_000_000_000)


class PurchaseReceiptRequest(BaseModel):
    lines: list[ReceiptLineInput] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_lines(self) -> "PurchaseReceiptRequest":
        line_ids = [line.purchase_order_line_id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("Each purchase order line may appear only once per receipt")
        return self


def _audit(db: Session, principal: TenantPrincipal, action: str, resource_type: str, resource_id: UUID) -> None:
    db.add(AuditEvent(
        tenant_id=principal.tenant.id, actor_user_id=principal.user.id,
        action=action, resource_type=resource_type, resource_id=str(resource_id), outcome="success",
    ))


def _supplier_dict(item: Supplier) -> dict:
    return {
        "id": str(item.id), "code": item.code, "name": item.name,
        "email": item.email, "phone": item.phone,
        "payment_terms_days": item.payment_terms_days, "is_active": item.is_active,
    }


def _order_dict(order: PurchaseOrder, lines: list[PurchaseOrderLine]) -> dict:
    return {
        "id": str(order.id), "order_number": order.order_number,
        "supplier_id": str(order.supplier_id), "warehouse_id": str(order.warehouse_id),
        "status": order.status, "notes": order.notes,
        "approved_at": order.approved_at.isoformat() if order.approved_at else None,
        "lines": [{
            "id": str(line.id), "product_id": str(line.product_id),
            "quantity_ordered": line.quantity_ordered,
            "quantity_received": line.quantity_received,
            "quantity_outstanding": line.quantity_ordered - line.quantity_received,
            "unit_cost_minor": line.unit_cost_minor,
        } for line in lines],
        "created_at": order.created_at.isoformat(),
    }


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierCreateRequest,
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    supplier = Supplier(
        tenant_id=principal.tenant.id, code=payload.code, name=payload.name,
        email=payload.email, phone=payload.phone, payment_terms_days=payload.payment_terms_days,
    )
    db.add(supplier)
    try:
        db.flush()
        _audit(db, principal, "procurement.supplier_created", "supplier", supplier.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Supplier code already exists in this tenant") from exc
    db.refresh(supplier)
    return _supplier_dict(supplier)


@router.get("/suppliers")
def list_suppliers(
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.read")),
    db: Session = Depends(get_db_session),
    active_only: bool = True,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(Supplier).where(Supplier.tenant_id == principal.tenant.id)
    if active_only:
        statement = statement.where(Supplier.is_active.is_(True))
    items = db.scalars(statement.order_by(Supplier.name, Supplier.code).offset(offset).limit(limit)).all()
    return {"items": [_supplier_dict(item) for item in items], "limit": limit, "offset": offset}


@router.post("/purchase-orders", status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    payload: PurchaseOrderCreateRequest,
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    supplier = db.scalar(select(Supplier).where(
        Supplier.id == payload.supplier_id, Supplier.tenant_id == principal.tenant.id, Supplier.is_active.is_(True)
    ))
    warehouse = db.scalar(select(Warehouse).where(
        Warehouse.id == payload.warehouse_id, Warehouse.tenant_id == principal.tenant.id, Warehouse.is_active.is_(True)
    ))
    if supplier is None or warehouse is None:
        raise HTTPException(status_code=404, detail="Active supplier or warehouse not found in this tenant")
    products = db.scalars(select(Product).where(
        Product.tenant_id == principal.tenant.id, Product.is_active.is_(True),
        Product.id.in_([line.product_id for line in payload.lines]),
    )).all()
    if len(products) != len(payload.lines):
        raise HTTPException(status_code=404, detail="One or more active products were not found in this tenant")
    order_id = uuid4()
    now = datetime.now(UTC)
    order = PurchaseOrder(
        id=order_id, tenant_id=principal.tenant.id, supplier_id=supplier.id, warehouse_id=warehouse.id,
        order_number=f"PO-{now:%Y%m%d}-{str(order_id)[:8].upper()}",
        status="draft", notes=payload.notes, created_by_user_id=principal.user.id,
    )
    lines = [
        PurchaseOrderLine(
            tenant_id=principal.tenant.id, purchase_order_id=order_id, product_id=line.product_id,
            quantity_ordered=line.quantity, quantity_received=0, unit_cost_minor=line.unit_cost_minor,
        ) for line in payload.lines
    ]
    db.add(order)
    db.add_all(lines)
    try:
        db.flush()
        _audit(db, principal, "procurement.purchase_order_created", "purchase_order", order.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Purchase order conflicts with existing records") from exc
    db.refresh(order)
    return _order_dict(order, lines)


@router.get("/purchase-orders")
def list_purchase_orders(
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.read")),
    db: Session = Depends(get_db_session),
    order_status: str | None = Query(default=None, pattern="^(draft|approved|partially_received|received|cancelled)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(PurchaseOrder).where(PurchaseOrder.tenant_id == principal.tenant.id)
    if order_status:
        statement = statement.where(PurchaseOrder.status == order_status)
    orders = db.scalars(statement.order_by(PurchaseOrder.created_at.desc()).offset(offset).limit(limit)).all()
    result = []
    for order in orders:
        lines = db.scalars(select(PurchaseOrderLine).where(
            PurchaseOrderLine.tenant_id == principal.tenant.id,
            PurchaseOrderLine.purchase_order_id == order.id,
        ).order_by(PurchaseOrderLine.id)).all()
        result.append(_order_dict(order, lines))
    return {"items": result, "limit": limit, "offset": offset}


@router.post("/purchase-orders/{order_id}/approve")
def approve_purchase_order(
    order_id: UUID,
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.approve")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    order = db.scalar(select(PurchaseOrder).where(
        PurchaseOrder.id == order_id, PurchaseOrder.tenant_id == principal.tenant.id
    ).with_for_update())
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if order.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft purchase orders can be approved")
    order.status = "approved"
    order.approved_by_user_id = principal.user.id
    order.approved_at = datetime.now(UTC)
    order.updated_at = datetime.now(UTC)
    _audit(db, principal, "procurement.purchase_order_approved", "purchase_order", order.id)
    db.commit()
    lines = db.scalars(select(PurchaseOrderLine).where(
        PurchaseOrderLine.tenant_id == principal.tenant.id, PurchaseOrderLine.purchase_order_id == order.id
    )).all()
    return _order_dict(order, lines)


@router.post("/purchase-orders/{order_id}/receipts", status_code=status.HTTP_201_CREATED)
def receive_purchase_order(
    order_id: UUID,
    payload: PurchaseReceiptRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    principal: TenantPrincipal = Depends(require_module("procurement", "procurement.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="Idempotency-Key cannot be blank")
    canonical = {
        "order_id": str(order_id),
        "lines": sorted(
            [{"line_id": str(item.purchase_order_line_id), "quantity": item.quantity} for item in payload.lines],
            key=lambda item: item["line_id"],
        ),
    }
    request_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    replay = db.scalar(select(ProcurementReceipt).where(
        ProcurementReceipt.tenant_id == principal.tenant.id, ProcurementReceipt.idempotency_key == key
    ))
    if replay is not None:
        if replay.request_hash != request_hash:
            raise HTTPException(status_code=409, detail="Idempotency-Key was used for a different receipt")
        return {"receipt_id": str(replay.id), "purchase_order_id": str(replay.purchase_order_id), "replayed": True}

    order = db.scalar(select(PurchaseOrder).where(
        PurchaseOrder.id == order_id, PurchaseOrder.tenant_id == principal.tenant.id
    ).with_for_update())
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if order.status not in {"approved", "partially_received"}:
        raise HTTPException(status_code=409, detail="Purchase order must be approved before receiving")
    receipt = ProcurementReceipt(
        tenant_id=principal.tenant.id, purchase_order_id=order.id, idempotency_key=key,
        request_hash=request_hash, created_by_user_id=principal.user.id,
    )
    db.add(receipt)
    try:
        db.flush()
        receipt_total_minor = 0
        for received_line in payload.lines:
            line = db.scalar(select(PurchaseOrderLine).where(
                PurchaseOrderLine.id == received_line.purchase_order_line_id,
                PurchaseOrderLine.tenant_id == principal.tenant.id,
                PurchaseOrderLine.purchase_order_id == order.id,
            ).with_for_update())
            if line is None:
                raise HTTPException(status_code=404, detail="Purchase order line not found")
            if received_line.quantity > line.quantity_ordered - line.quantity_received:
                raise HTTPException(status_code=409, detail="Receipt quantity exceeds outstanding purchase quantity")
            product = db.scalar(select(Product).where(
                Product.id == line.product_id, Product.tenant_id == principal.tenant.id, Product.is_active.is_(True)
            ))
            warehouse = db.scalar(select(Warehouse).where(
                Warehouse.id == order.warehouse_id, Warehouse.tenant_id == principal.tenant.id,
                Warehouse.is_active.is_(True)
            ))
            if product is None or warehouse is None:
                raise HTTPException(status_code=409, detail="Product or receiving warehouse is no longer active")
            values = {
                "tenant_id": principal.tenant.id, "warehouse_id": warehouse.id, "product_id": product.id,
                "quantity_on_hand": 0, "updated_at": datetime.now(UTC),
            }
            dialect = db.get_bind().dialect.name
            if dialect == "postgresql":
                statement = postgresql_insert(InventoryBalance).values(**values).on_conflict_do_nothing(
                    index_elements=["tenant_id", "warehouse_id", "product_id"]
                )
            elif dialect == "sqlite":
                statement = sqlite_insert(InventoryBalance).values(**values).on_conflict_do_nothing(
                    index_elements=["tenant_id", "warehouse_id", "product_id"]
                )
            else:
                raise HTTPException(status_code=503, detail="Unsupported inventory database")
            db.execute(statement)
            balance = db.scalar(select(InventoryBalance).where(
                InventoryBalance.tenant_id == principal.tenant.id,
                InventoryBalance.warehouse_id == warehouse.id,
                InventoryBalance.product_id == product.id,
            ).with_for_update())
            if balance is None:
                raise HTTPException(status_code=503, detail="Inventory balance could not be locked")
            movement = InventoryMovement(
                tenant_id=principal.tenant.id, warehouse_id=warehouse.id, product_id=product.id,
                movement_type="receipt", quantity_delta=received_line.quantity,
                idempotency_key=f"po-receipt:{receipt.id}:{line.id}",
                request_hash=hashlib.sha256(f"{receipt.id}:{line.id}:{received_line.quantity}".encode()).hexdigest(),
                reference=f"{order.order_number}/receipt/{receipt.id}",
                created_by_user_id=principal.user.id,
            )
            db.add(movement)
            db.flush()
            enqueue_outbox_event(
                db, tenant_id=principal.tenant.id, event_type="inventory.movement.created",
                aggregate_type="inventory_movement", aggregate_id=str(movement.id),
                dedupe_key=f"inventory-movement:{movement.id}",
                payload={
                    "movement_id": str(movement.id), "purchase_order_id": str(order.id),
                    "receipt_id": str(receipt.id), "warehouse_id": str(warehouse.id),
                    "product_id": str(product.id), "movement_type": "receipt",
                    "quantity_delta": received_line.quantity,
                },
            )
            line.quantity_received += received_line.quantity
            receipt_total_minor += received_line.quantity * line.unit_cost_minor
        if receipt_total_minor > 0:
            accounting = db.scalar(select(ProcurementAccountingSettings).where(
                ProcurementAccountingSettings.tenant_id == principal.tenant.id
            ))
            if accounting is None:
                raise HTTPException(status_code=409, detail="Procurement accounting settings must be configured before receiving goods")
            if receipt_total_minor > 2_147_483_647:
                raise HTTPException(status_code=409, detail="Receipt value exceeds the general-ledger integer limit")
            create_journal_entry(
                db,
                tenant_id=principal.tenant.id,
                actor_user_id=principal.user.id,
                idempotency_key=f"procurement-receipt:{receipt.id}",
                currency=accounting.base_currency,
                description=f"Goods received for {order.order_number}"[:500],
                posting_date=datetime.now(UTC).date(),
                lines=[
                    {
                        "account_code": accounting.inventory_account_code,
                        "memo": "Inventory received",
                        "debit_minor": receipt_total_minor,
                        "credit_minor": 0,
                    },
                    {
                        "account_code": accounting.grni_account_code,
                        "memo": "Goods received not invoiced",
                        "debit_minor": 0,
                        "credit_minor": receipt_total_minor,
                    },
                ],
                commit=False,
            )
        all_lines = db.scalars(select(PurchaseOrderLine).where(
            PurchaseOrderLine.tenant_id == principal.tenant.id,
            PurchaseOrderLine.purchase_order_id == order.id,
        )).all()
        order.status = "received" if all(
            item.quantity_received == item.quantity_ordered for item in all_lines
        ) else "partially_received"
        order.updated_at = datetime.now(UTC)
        _audit(db, principal, "procurement.purchase_order_received", "purchase_order", order.id)
        _audit(db, principal, "procurement.goods_received", "procurement_receipt", receipt.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        concurrent_replay = db.scalar(
            select(ProcurementReceipt).where(
                ProcurementReceipt.tenant_id == principal.tenant.id,
                ProcurementReceipt.idempotency_key == key,
            )
        )
        if concurrent_replay is not None:
            if concurrent_replay.request_hash != request_hash:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was used for a different receipt",
                ) from exc
            return {
                "receipt_id": str(concurrent_replay.id),
                "purchase_order_id": str(concurrent_replay.purchase_order_id),
                "replayed": True,
            }
        raise HTTPException(status_code=409, detail="Receipt conflicts with existing inventory records") from exc
    except (AccountingPeriodConflictError, JournalConflictError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        db.rollback()
        raise
    return {
        "receipt_id": str(receipt.id), "purchase_order_id": str(order.id),
        "order_number": order.order_number, "status": order.status, "replayed": False,
    }


@router.post("/preview")
def preview_replenishment(
    payload: ProcurementPreviewRequest,
    _principal: TenantPrincipal = Depends(require_module("procurement", "procurement.read")),
) -> dict:
    ranked = rank_supplier_quotes([SupplierQuote(**quote.model_dump()) for quote in payload.suppliers])
    chosen = ranked[0] if ranked else None
    data = ReplenishmentInput(
        demand_history=[
            DemandPoint(units=point.units, stockout_censored=point.stockout_censored, promotion=point.promotion)
            for point in payload.demand_history
        ],
        sellable_on_hand=payload.sellable_on_hand,
        reserved_units=payload.reserved_units,
        confirmed_inbound=payload.confirmed_inbound,
        backordered_units=payload.backordered_units,
        lead_time_days=chosen.lead_time_days if chosen else payload.lead_time_days,
        lead_time_std_days=chosen.lead_time_std_days if chosen else Decimal("0"),
        review_period_days=payload.review_period_days,
        service_level=payload.service_level,
        minimum_order_quantity=payload.minimum_order_quantity,
        order_multiple=payload.order_multiple,
        shelf_life_days=payload.shelf_life_days,
        storage_capacity_units=payload.storage_capacity_units,
        budget_minor=payload.budget_minor,
        supplier_capacity_units=chosen.capacity_units if chosen else None,
    )
    result = calculate_replenishment(data, chosen.landed_unit_cost_minor if chosen else 0)
    transfers = []
    remaining = result.suggested_quantity
    for branch in payload.source_branches:
        amount = transferable_quantity(branch.sellable_units, branch.reserved_units, branch.safety_stock_units, remaining)
        if amount > 0:
            transfers.append({"source_branch_id": branch.branch_id, "suggested_units": str(amount)})
            remaining -= amount
        if remaining <= 0:
            break
    return {
        "product_id": str(payload.product_id), "warehouse_id": str(payload.warehouse_id),
        "forecast_daily_demand": str(result.forecast_daily_demand), "demand_stddev": str(result.demand_stddev),
        "inventory_position": str(result.inventory_position), "safety_stock": str(result.safety_stock),
        "reorder_point": str(result.reorder_point), "suggested_purchase_quantity": str(remaining),
        "suggested_transfer_quantity": str(result.suggested_quantity - remaining),
        "selected_supplier_id": chosen.supplier_id if chosen else None,
        "estimated_cost_minor": int((remaining * (chosen.landed_unit_cost_minor if chosen else 0)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )),
        "priority_score": str(result.priority_score), "confidence": result.confidence,
        "reasons": list(result.reasons),
        "supplier_candidates": [{
            "supplier_id": quote.supplier_id, "landed_unit_cost_minor": quote.landed_unit_cost_minor,
            "lead_time_days": quote.lead_time_days, "on_time_rate": str(quote.on_time_rate),
            "quality_acceptance_rate": str(quote.quality_acceptance_rate),
        } for quote in ranked],
        "transfer_suggestions": transfers, "requires_human_approval": True, "creates_purchase_order": False,
    }
