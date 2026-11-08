from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from backend.app.identity.api_dependencies import TenantPrincipal, require_permission
from backend.app.procurement.engine import (
    DemandPoint,
    ReplenishmentInput,
    SupplierQuote,
    calculate_replenishment,
    rank_supplier_quotes,
    transferable_quantity,
)

router = APIRouter(prefix="/procurement", tags=["smart-procurement"])
Positive = Annotated[Decimal, Field(ge=0)]
StrictlyPositive = Annotated[Decimal, Field(gt=0)]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


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


@router.post("/preview")
def preview_replenishment(
    payload: ProcurementPreviewRequest,
    _principal: TenantPrincipal = Depends(require_permission("procurement.read")),
) -> dict:
    ranked = rank_supplier_quotes([
        SupplierQuote(**quote.model_dump()) for quote in payload.suppliers
    ])
    chosen = ranked[0] if ranked else None
    data = ReplenishmentInput(
        demand_history=[
            DemandPoint(
                units=point.units,
                stockout_censored=point.stockout_censored,
                promotion=point.promotion,
            )
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
    result = calculate_replenishment(
        data,
        chosen.landed_unit_cost_minor if chosen else 0,
    )
    transfers = []
    remaining = result.suggested_quantity
    for branch in payload.source_branches:
        amount = transferable_quantity(
            branch.sellable_units,
            branch.reserved_units,
            branch.safety_stock_units,
            remaining,
        )
        if amount > 0:
            transfers.append({"source_branch_id": branch.branch_id, "suggested_units": str(amount)})
            remaining -= amount
        if remaining <= 0:
            break
    return {
        "product_id": str(payload.product_id),
        "warehouse_id": str(payload.warehouse_id),
        "forecast_daily_demand": str(result.forecast_daily_demand),
        "demand_stddev": str(result.demand_stddev),
        "inventory_position": str(result.inventory_position),
        "safety_stock": str(result.safety_stock),
        "reorder_point": str(result.reorder_point),
        "suggested_purchase_quantity": str(remaining),
        "suggested_transfer_quantity": str(result.suggested_quantity - remaining),
        "selected_supplier_id": chosen.supplier_id if chosen else None,
        "estimated_cost_minor": int(
            (remaining * (chosen.landed_unit_cost_minor if chosen else 0)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        ),
        "priority_score": str(result.priority_score),
        "confidence": result.confidence,
        "reasons": list(result.reasons),
        "supplier_candidates": [
            {
                "supplier_id": quote.supplier_id,
                "landed_unit_cost_minor": quote.landed_unit_cost_minor,
                "lead_time_days": quote.lead_time_days,
                "on_time_rate": str(quote.on_time_rate),
                "quality_acceptance_rate": str(quote.quality_acceptance_rate),
            }
            for quote in ranked
        ],
        "transfer_suggestions": transfers,
        "requires_human_approval": True,
        "creates_purchase_order": False,
    }
