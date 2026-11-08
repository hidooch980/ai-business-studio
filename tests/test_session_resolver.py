from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from retail_app.api.session_resolver import PostgresSessionResolver, SessionCookieSettings
from retail_app.security.authorization import Role

TENANT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SUBJECT = UUID("aaaaaaaa-1001-4000-8000-000000000001")
SESSION = UUID("aaaaaaaa-2001-4000-8000-000000000001")
BRANCH = UUID("aaaaaaaa-0001-4000-8000-000000000001")
TOKEN = "A" * 48


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.row


class FakeConnection:
    def __init__(self, *, membership=("owner_admin",), identity=(True,), tenant=("active",),
                 session=(SESSION,), branches=((BRANCH,),), bootstrap=(TENANT, SUBJECT, SESSION)):
        self.membership = membership
        self.identity = identity
        self.tenant = tenant
        self.session = session
        self.branches = branches
        self.bootstrap = bootstrap
        self.statements = []

    def execute(self, query, params=None):
        self.statements.append((query, params))
        if "resolve_auth_session_bootstrap" in query:
            return FakeCursor(self.bootstrap)
        if "set_config" in query:
            return FakeCursor(("ok",))
        if "FROM auth_sessions" in query:
            return FakeCursor(self.session)
        if "FROM identities" in query:
            return FakeCursor(self.identity)
        if "FROM tenants" in query:
            return FakeCursor(self.tenant)
        if "FROM tenant_memberships" in query:
            return FakeCursor(self.membership)
        if "FROM branch_memberships" in query:
            return FakeCursor(self.branches)
        raise AssertionError(f"unexpected query: {query}")


class FakeDatabase:
    def __init__(self, connection):
        self.connection = connection

    class _Tx:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self.connection

        def __exit__(self, *args):
            return False

    def transaction(self):
        return self._Tx(self.connection)


def request(token=TOKEN):
    cookies = {"__Host-retail_session": token} if token is not None else {}
    return SimpleNamespace(cookies=cookies)


def test_resolver_uses_cookie_hash_and_database_role_and_branch_membership():
    connection = FakeConnection()
    context = PostgresSessionResolver(FakeDatabase(connection))(request())
    assert context.subject_id == str(SUBJECT)
    assert context.tenant_id == str(TENANT)
    assert context.role is Role.OWNER_ADMIN
    assert context.branch_ids == frozenset({str(BRANCH)})
    bootstrap_call = next(x for x in connection.statements if "resolve_auth_session_bootstrap" in x[0])
    assert bootstrap_call[1][0] != TOKEN.encode()
    assert len(bootstrap_call[1][0]) == 32
    assert sum("set_config" in x[0] for x in connection.statements) == 2


@pytest.mark.parametrize("cookie", [None, "", "bad", "x" * 513])
def test_resolver_rejects_missing_or_malformed_cookie(cookie):
    with pytest.raises(HTTPException) as error:
        PostgresSessionResolver(FakeDatabase(FakeConnection()))(request(cookie))
    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"bootstrap": None}, 401),
        ({"session": None}, 401),
        ({"identity": (False,)}, 401),
        ({"tenant": ("suspended",)}, 403),
        ({"membership": None}, 403),
        ({"membership": ("forged_admin",)}, 403),
    ],
)
def test_resolver_fails_closed_for_invalid_current_database_state(overrides, expected):
    with pytest.raises(HTTPException) as error:
        PostgresSessionResolver(FakeDatabase(FakeConnection(**overrides)))(request())
    assert error.value.status_code == expected


def test_role_is_loaded_from_current_membership_not_cookie_claims():
    context = PostgresSessionResolver(
        FakeDatabase(FakeConnection(membership=("employee",)))
    )(request())
    assert context.role is Role.EMPLOYEE


def test_revoked_branch_membership_is_not_returned():
    context = PostgresSessionResolver(
        FakeDatabase(FakeConnection(branches=()))
    )(request())
    assert context.branch_ids == frozenset()


def test_cookie_configuration_enforces_host_prefix_requirements():
    with pytest.raises(ValueError):
        PostgresSessionResolver(
            FakeDatabase(FakeConnection()),
            SessionCookieSettings(secure=False),
        )


@pytest.mark.parametrize(
    "settings",
    [
        SessionCookieSettings(httponly=False),
        SessionCookieSettings(samesite="lax"),
        SessionCookieSettings(path="/api"),
    ],
)
def test_cookie_settings_reject_weak_browser_cookie_flags(settings):
    with pytest.raises(ValueError):
        PostgresSessionResolver(FakeDatabase(FakeConnection()), settings)
