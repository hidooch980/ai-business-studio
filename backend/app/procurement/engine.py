"""Deterministic, explainable replenishment calculations.

The engine is deliberately independent of persistence and ML libraries so the
same rules can be tested, backtested, and used as a safe fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from statistics import mean, pstdev
from typing import Sequence

D = Decimal
_SERVICE_Z = {D("0.90"): D("1.282"), D("0.95"): D("1.645"), D("0.97"): D("1.881"), D("0.99"): D("2.326")}


@dataclass(frozen=True)
class DemandPoint:
    units: Decimal
    stockout_censored: bool = False
    promotion: bool = False


@dataclass(frozen=True)
class SupplierQuote:
    supplier_id: str
    unit_cost_minor: int
    freight_per_unit_minor: int = 0
    lead_time_days: int = 1
    lead_time_std_days: Decimal = D("0")
    on_time_rate: Decimal = D("1")
    quality_acceptance_rate: Decimal = D("1")
    payment_terms_days: int = 0
    capacity_units: int | None = None
    approved: bool = True

    @property
    def landed_unit_cost_minor(self) -> int:
        return self.unit_cost_minor + self.freight_per_unit_minor


@dataclass(frozen=True)
class ReplenishmentInput:
    demand_history: Sequence[DemandPoint]
    sellable_on_hand: Decimal
    reserved_units: Decimal = D("0")
    confirmed_inbound: Decimal = D("0")
    backordered_units: Decimal = D("0")
    lead_time_days: int = 1
    review_period_days: int = 7
    service_level: Decimal = D("0.95")
    minimum_order_quantity: Decimal = D("1")
    order_multiple: Decimal = D("1")
    shelf_life_days: int | None = None
    storage_capacity_units: Decimal | None = None
    budget_minor: int | None = None
    supplier_capacity_units: Decimal | None = None


@dataclass(frozen=True)
class ReplenishmentResult:
    forecast_daily_demand: Decimal
    demand_stddev: Decimal
    inventory_position: Decimal
    safety_stock: Decimal
    reorder_point: Decimal
    suggested_quantity: Decimal
    estimated_cost_minor: int
    priority_score: Decimal
    confidence: str
    reasons: tuple[str, ...]


def _ceil_to_multiple(value: Decimal, multiple: Decimal) -> Decimal:
    if multiple <= 0:
        raise ValueError("order_multiple must be positive")
    return (value / multiple).to_integral_value(rounding=ROUND_CEILING) * multiple


def forecast_daily_demand(history: Sequence[DemandPoint]) -> tuple[Decimal, Decimal, str]:
    """Use clean non-promotion observations; recent 7-day mean is weighted 2x."""
    clean = [p.units for p in history if not p.stockout_censored and not p.promotion and p.units >= 0]
    if not clean:
        return D("0"), D("0"), "low"
    recent = clean[-7:]
    older = clean[-28:-7]
    if older:
        forecast = (D("2") * D(str(mean(recent))) + D(str(mean(older)))) / D("3")
    else:
        forecast = D(str(mean(recent)))
    spread = D(str(pstdev(clean))) if len(clean) > 1 else D("0")
    confidence = "high" if len(clean) >= 28 else "medium" if len(clean) >= 7 else "low"
    return max(forecast, D("0")), spread, confidence


def calculate_replenishment(data: ReplenishmentInput, landed_unit_cost_minor: int) -> ReplenishmentResult:
    if data.lead_time_days < 0 or data.review_period_days < 0:
        raise ValueError("lead time and review period cannot be negative")
    if data.minimum_order_quantity <= 0 or data.order_multiple <= 0:
        raise ValueError("MOQ and order multiple must be positive")
    if landed_unit_cost_minor < 0:
        raise ValueError("landed unit cost cannot be negative")
    if not D("0") < data.service_level < D("1"):
        raise ValueError("service level must be between 0 and 1")
    if data.sellable_on_hand < 0 or data.reserved_units < 0 or data.confirmed_inbound < 0 or data.backordered_units < 0:
        raise ValueError("inventory quantities cannot be negative")
    if data.supplier_capacity_units is not None and data.supplier_capacity_units < 0:
        raise ValueError("supplier capacity cannot be negative")

    forecast, demand_stddev, confidence = forecast_daily_demand(data.demand_history)
    z = min(_SERVICE_Z.items(), key=lambda item: abs(item[0] - data.service_level))[1]
    lead = D(data.lead_time_days)
    review = D(data.review_period_days)
    inventory_position = data.sellable_on_hand + data.confirmed_inbound - data.reserved_units - data.backordered_units
    safety_stock = z * demand_stddev * lead.sqrt() if lead else D("0")
    reorder_point = forecast * lead + safety_stock
    target_days = lead + review
    target_stock = forecast * target_days + safety_stock
    raw_need = max(D("0"), target_stock - inventory_position)

    if data.shelf_life_days is not None:
        if data.shelf_life_days <= 0:
            raise ValueError("shelf life must be positive")
        raw_need = min(raw_need, forecast * D(data.shelf_life_days))
    if data.storage_capacity_units is not None:
        if data.storage_capacity_units < 0:
            raise ValueError("storage capacity cannot be negative")
        raw_need = min(raw_need, max(D("0"), data.storage_capacity_units - data.sellable_on_hand))
    if data.supplier_capacity_units is not None:
        raw_need = min(raw_need, data.supplier_capacity_units)

    quantity = D("0") if raw_need == 0 else max(data.minimum_order_quantity, _ceil_to_multiple(raw_need, data.order_multiple))
    if landed_unit_cost_minor and data.budget_minor is not None:
        if data.budget_minor < 0:
            raise ValueError("budget cannot be negative")
        affordable = D(data.budget_minor) / D(landed_unit_cost_minor)
        quantity = min(quantity, (affordable / data.order_multiple).to_integral_value(rounding="ROUND_FLOOR") * data.order_multiple)
        if quantity < data.minimum_order_quantity:
            quantity = D("0")
    estimated_cost = int(quantity * landed_unit_cost_minor)
    urgency_days = (inventory_position / forecast) if forecast > 0 else D("Infinity")
    urgency = D("100") if urgency_days <= lead else D("70") if urgency_days <= lead + 3 else D("40") if urgency_days <= lead + 7 else D("10")
    score = min(D("100"), urgency + min(D("20"), forecast * D("2")))
    reasons = [
        f"forecast_daily_demand={forecast}",
        f"inventory_position={inventory_position}",
        f"reorder_point={reorder_point}",
        f"safety_stock={safety_stock}",
        f"lead_time_days={data.lead_time_days}",
        f"review_period_days={data.review_period_days}",
    ]
    if any(p.stockout_censored for p in data.demand_history):
        reasons.append("stockout_censored_days_excluded_from_forecast")
    if any(p.promotion for p in data.demand_history):
        reasons.append("promotion_days_excluded_from_baseline_forecast")
    if quantity == 0 and raw_need > 0:
        reasons.append("quantity_limited_by_budget_or_supplier_constraints")
    return ReplenishmentResult(
        forecast_daily_demand=forecast,
        demand_stddev=demand_stddev,
        inventory_position=inventory_position,
        safety_stock=safety_stock,
        reorder_point=reorder_point,
        suggested_quantity=quantity,
        estimated_cost_minor=estimated_cost,
        priority_score=score,
        confidence=confidence,
        reasons=tuple(reasons),
    )


def rank_supplier_quotes(quotes: Sequence[SupplierQuote]) -> list[SupplierQuote]:
    """Rank approved quotes by landed cost adjusted for delivery and quality risk."""
    eligible = [q for q in quotes if q.approved and q.unit_cost_minor >= 0 and q.freight_per_unit_minor >= 0]
    return sorted(
        eligible,
        key=lambda q: (
            D(q.landed_unit_cost_minor)
            * (D("1") + (D("1") - q.on_time_rate) + (D("1") - q.quality_acceptance_rate)),
            q.lead_time_days,
            -q.payment_terms_days,
            q.supplier_id,
        ),
    )


def transferable_quantity(
    source_sellable: Decimal,
    source_reserved: Decimal,
    source_safety_stock: Decimal,
    destination_need: Decimal,
) -> Decimal:
    """Only transfer stock that remains above the source branch's own safety stock."""
    available_surplus = max(D("0"), source_sellable - source_reserved - source_safety_stock)
    return min(available_surplus, max(D("0"), destination_need))
