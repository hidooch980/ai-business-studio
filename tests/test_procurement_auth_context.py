from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from retail_app.api.auth_context import (
    mount_procurement_routes,
    require_authenticated_access_context,
)
from retail_app.security.authorization import AccessContext, Role


def _request(resolver=None):
    state = SimpleNamespace()
    if resolver is not None:
        state.access_context_resolver = resolver
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_missing_host_resolver_fails_closed():
    with pytest.raises(HTTPException) as error:
        asyncio.run(require_authenticated_access_context(_request()))
    assert error.value.status_code == 503


def test_resolver_must_return_active_access_context():
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            require_authenticated_access_context(
                _request(lambda _request: None)
            )
        )
    assert error.value.status_code == 401

    inactive = AccessContext("subject", "tenant", Role.OWNER_ADMIN, active=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            require_authenticated_access_context(
                _request(lambda _request: inactive)
            )
        )
    assert error.value.status_code == 401


def test_authenticated_context_is_returned_from_trusted_resolver():
    expected = AccessContext(
        "subject", "tenant", Role.BRANCH_MANAGER, frozenset({"branch-1"})
    )
    actual = asyncio.run(
        require_authenticated_access_context(
            _request(lambda _request: expected)
        )
    )
    assert actual is expected
    assert actual.role is Role.BRANCH_MANAGER
    assert actual.branch_ids == frozenset({"branch-1"})


def test_async_host_resolver_is_supported():
    expected = AccessContext("subject", "tenant", Role.OWNER_ADMIN)

    async def resolver(_request):
        return expected

    actual = asyncio.run(
        require_authenticated_access_context(_request(resolver))
    )
    assert actual is expected


def test_mount_requires_explicit_resolver_and_mounts_routes():
    app = FastAPI()
    with pytest.raises(TypeError):
        mount_procurement_routes(app, object(), access_context_resolver=None)

    mount_procurement_routes(
        app,
        object(),
        access_context_resolver=lambda _request: AccessContext(
            "subject", "tenant", Role.OWNER_ADMIN
        ),
    )
    paths = {route.path for route in app.routes}
    assert "/api/procurement/suppliers" in paths
    assert "/api/procurement/supplier-payments" in paths

    with pytest.raises(RuntimeError):
        mount_procurement_routes(
            app,
            object(),
            access_context_resolver=lambda _request: AccessContext(
                "subject", "tenant", Role.OWNER_ADMIN
            ),
        )
