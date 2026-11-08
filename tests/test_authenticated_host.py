from fastapi import FastAPI

from retail_app.api.authenticated_host import mount_authenticated_procurement_routes
from retail_app.api.session_resolver import PostgresSessionResolver


class UnusedDatabase:
    pass


def test_fastapi_host_mounts_authenticated_procurement_routes_once():
    app = FastAPI()
    resolver = PostgresSessionResolver(UnusedDatabase())

    mounted = mount_authenticated_procurement_routes(
        app, UnusedDatabase(), session_resolver=resolver
    )
    assert mounted is resolver
    assert app.state.session_resolver is resolver
    paths = {route.path for route in app.routes}
    assert "/api/procurement/purchase-orders" in paths
    assert "/api/procurement/suppliers" in paths

    route_count = len(app.routes)
    assert mount_authenticated_procurement_routes(app, UnusedDatabase()) is resolver
    assert len(app.routes) == route_count
