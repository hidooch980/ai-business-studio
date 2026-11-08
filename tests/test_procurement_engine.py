from decimal import Decimal as D

import pytest

from backend.app.procurement.engine import (
    DemandPoint,
    ReplenishmentInput,
    SupplierQuote,
    calculate_replenishment,
    forecast_daily_demand,
    rank_supplier_quotes,
    transferable_quantity,
)


def test_forecast_excludes_stockout_and_promotion_censored_days():
    history = [DemandPoint(D("10")) for _ in range(10)]
    history += [DemandPoint(D("100"), stockout_censored=True), DemandPoint(D("90"), promotion=True)]
    forecast, _, confidence = forecast_daily_demand(history)
    assert forecast == D("10")
    assert confidence == "medium"


def test_replenishment_subtracts_reservations_and_adds_confirmed_inbound():
    result = calculate_replenishment(
        ReplenishmentInput(
            demand_history=[DemandPoint(D("10"))] * 14,
            sellable_on_hand=D("50"),
            reserved_units=D("10"),
            confirmed_inbound=D("20"),
            lead_time_days=3,
            review_period_days=7,
            minimum_order_quantity=D("5"),
            order_multiple=D("5"),
        ),
        landed_unit_cost_minor=100,
    )
    assert result.inventory_position == D("60")
    assert result.suggested_quantity == D("45")
    assert result.estimated_cost_minor == 4500
    assert result.confidence == "medium"


def test_budget_caps_quantity_without_violating_order_multiple():
    result = calculate_replenishment(
        ReplenishmentInput(
            demand_history=[DemandPoint(D("5"))] * 30,
            sellable_on_hand=D("0"),
            lead_time_days=2,
            review_period_days=7,
            minimum_order_quantity=D("1"),
            order_multiple=D("6"),
            budget_minor=2500,
        ),
        landed_unit_cost_minor=100,
    )
    assert result.suggested_quantity == D("24")
    assert result.estimated_cost_minor <= 2500


def test_shelf_life_and_storage_capacity_cap_order():
    result = calculate_replenishment(
        ReplenishmentInput(
            demand_history=[DemandPoint(D("4"))] * 30,
            sellable_on_hand=D("10"),
            lead_time_days=2,
            review_period_days=14,
            shelf_life_days=3,
            storage_capacity_units=D("15"),
        ),
        landed_unit_cost_minor=50,
    )
    assert result.suggested_quantity <= D("5")


def test_supplier_rank_uses_landed_cost_quality_and_reliability():
    quotes = [
        SupplierQuote("cheap-unreliable", 80, 0, 2, on_time_rate=D("0.5"), quality_acceptance_rate=D("0.7")),
        SupplierQuote("reliable", 95, 2, 3, on_time_rate=D("0.99"), quality_acceptance_rate=D("0.99")),
        SupplierQuote("blocked", 1, approved=False),
    ]
    ranked = rank_supplier_quotes(quotes)
    assert [q.supplier_id for q in ranked] == ["reliable", "cheap-unreliable"]


def test_transfer_respects_source_safety_stock():
    assert transferable_quantity(D("100"), D("20"), D("30"), D("80")) == D("50")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lead_time_days": -1},
        {"minimum_order_quantity": D("0")},
        {"service_level": D("1")},
        {"sellable_on_hand": D("-1")},
    ],
)
def test_invalid_replenishment_inputs_fail_closed(kwargs):
    values = dict(
        demand_history=[DemandPoint(D("2"))] * 10,
        sellable_on_hand=D("10"),
        lead_time_days=3,
        review_period_days=7,
        minimum_order_quantity=D("1"),
        service_level=D("0.95"),
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        calculate_replenishment(ReplenishmentInput(**values), 100)
