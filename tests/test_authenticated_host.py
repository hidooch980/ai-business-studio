from __future__ import annotations

from retail_app.api.host import create_app
from retail_app.infrastructure.database import PostgresDatabase


def test_fastapi_host_mounts_protected_procurement_routes():
    app = create_app(PostgresDatabase("postgresql://unused"))
    paths = {route.path for route in app.routes}
    assert "/api/health" in paths
    assert "/api/procurement/suppliers" in paths
    assert "/api/procurement/supplier-payments" in paths
    assert callable(app.state.access_context_resolver)
