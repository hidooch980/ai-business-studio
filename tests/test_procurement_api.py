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
