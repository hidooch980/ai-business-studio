from datetime import date

import pytest

from retail_app.procurement.purchase_orders import PurchaseOrder, PurchaseOrderLine
from retail_app.procurement.suppliers import Supplier, SupplierStatus


def test_supplier_requires_tenant_and_legal_name():
    with pytest.raises(ValueError):
        Supplier(id="s-1", tenant_id="t-1", legal_name=" ")
    supplier = Supplier(id="s-1", tenant_id="t-1", legal_name="Supplier Co")
    assert supplier.status is SupplierStatus.ACTIVE


def test_purchase_order_calculates_exact_minor_unit_total():
    order = PurchaseOrder(
        id="po-1",
        tenant_id="t-1",
        branch_id="b-1",
        supplier_id="s-1",
        currency="EUR",
        order_date=date(2026, 11, 8),
        order_number="PO-001",
        lines=(
            PurchaseOrderLine(1, "item-1", "Bolts", 2000, 125),
            PurchaseOrderLine(2, "item-2", "Nuts", 1000, 75),
        ),
    )
    assert order.total_minor == 325


def test_purchase_order_rejects_fractional_minor_unit_total():
    line = PurchaseOrderLine(1, "item-1", "Part", 1, 1)
    with pytest.raises(ValueError, match="fractional minor units"):
        _ = line.line_total_minor


def test_purchase_order_rejects_duplicate_line_numbers():
    lines = (
        PurchaseOrderLine(1, "item-1", "Part A", 1000, 10),
        PurchaseOrderLine(1, "item-2", "Part B", 1000, 20),
    )
    with pytest.raises(ValueError, match="unique"):
        PurchaseOrder("po-1", "t-1", "b-1", "s-1", "EUR", date(2026, 11, 8), lines, "PO-001")


def test_purchase_order_requires_currency_and_lines():
    with pytest.raises(ValueError):
        PurchaseOrder("po-1", "t-1", "b-1", "s-1", "EURO", date(2026, 11, 8),
                      (PurchaseOrderLine(1, "i", "Part", 1000, 1),), "PO-002")
    with pytest.raises(ValueError):
        PurchaseOrder("po-2", "t-1", "b-1", "s-1", "EUR", date(2026, 11, 8), (), "PO-003")
