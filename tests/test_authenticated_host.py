from fastapi import FastAPI

from retail_app.api.app import create_app
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
    paths = set(app.openapi()["paths"])
    assert "/api/procurement/purchase-orders" in paths
    assert "/api/procurement/suppliers" in paths
    assert "/api/v1/auth/sessions" in paths
    assert "/api/v1/auth/sessions/{session_id}" in paths

    route_count = len(app.routes)
    assert mount_authenticated_procurement_routes(app, UnusedDatabase()) is resolver
    assert len(app.routes) == route_count



def test_app_factory_creates_fastapi_host_without_running_migrations():
    app = create_app(UnusedDatabase(), title="Test API")
    assert app.title == "Test API"
    assert isinstance(app.state.session_resolver, PostgresSessionResolver)
    paths = set(app.openapi()["paths"])
    assert "/api/procurement/purchase-orders" in paths
    assert "/api/v1/auth/sessions" in paths
