from retail_app.api.procurement import create_procurement_router
from retail_app.security.authorization import AccessContext, Role


def test_procurement_router_exposes_order_receipt_invoice_ap_and_payment_routes():
    actor = AccessContext("owner", "tenant-a", Role.OWNER_ADMIN)
    router = create_procurement_router(object(), lambda: actor)
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    expected = {
        ("/api/procurement/suppliers", ("POST",)),
        ("/api/procurement/purchase-orders", ("GET",)),
        ("/api/procurement/purchase-orders", ("POST",)),
        ("/api/procurement/purchase-orders/{order_id}", ("GET",)),
        ("/api/procurement/purchase-orders/{order_id}", ("PATCH",)),
        ("/api/procurement/purchase-orders/{order_id}/approve", ("POST",)),
        ("/api/procurement/purchase-orders/{order_id}/receipts", ("POST",)),
        ("/api/procurement/supplier-invoices/match", ("POST",)),
        ("/api/procurement/inventory/stock", ("GET",)),
        ("/api/procurement/accounts-payable", ("GET",)),
        ("/api/procurement/supplier-payments", ("POST",)),
    }
    assert expected <= routes

def test_procurement_api_rejects_naive_transaction_timestamps():
    from datetime import datetime

    import pytest
    from pydantic import ValidationError

    from retail_app.api.procurement import GoodsReceiptInput, SupplierPaymentInput

    with pytest.raises(ValidationError):
        GoodsReceiptInput(
            receipt_number="GR-1",
            received_at=datetime(2026, 11, 8, 12, 0),
            lines=[{
                "po_line_number": 1, "received_quantity_milli": 1000,
                "accepted_quantity_milli": 1000, "rejected_quantity_milli": 0,
            }],
        )
    with pytest.raises(ValidationError):
        SupplierPaymentInput(
            payment_id="not-a-uuid-yet",
            supplier_id="not-a-uuid-yet",
            payment_reference="PAY-1",
            currency="EUR",
            amount_minor=100,
            paid_at=datetime(2026, 11, 8, 12, 0),
            method="cash",
            allocations=[{"payable_id": "not-a-uuid-yet", "amount_minor": 100}],
        )


def test_procurement_api_maps_database_constraint_and_data_errors_safely():
    import pytest
    from fastapi import HTTPException

    from retail_app.api.procurement import _run

    class DatabaseError(Exception):
        def __init__(self, sqlstate):
            self.sqlstate = sqlstate

    with pytest.raises(HTTPException) as conflict:
        _run(lambda: (_ for _ in ()).throw(DatabaseError("23514")))
    assert conflict.value.status_code == 409
    assert "23514" not in conflict.value.detail

    with pytest.raises(HTTPException) as invalid:
        _run(lambda: (_ for _ in ()).throw(DatabaseError("22P02")))
    assert invalid.value.status_code == 422
    assert "22P02" not in invalid.value.detail
