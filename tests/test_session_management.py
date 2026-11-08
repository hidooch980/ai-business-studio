from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from retail_app.api.session_routes import create_session_router
from retail_app.security.authorization import AccessContext, Role
from retail_app.security.session_service import SessionService

TENANT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SUBJECT = "aaaaaaaa-1001-4000-8000-000000000001"
CURRENT = "aaaaaaaa-2001-4000-8000-000000000001"
TARGET = "aaaaaaaa-2002-4000-8000-000000000002"
TOKEN_HASH = b"t" * 32


class Result:
    def __init__(self, rows=(), one=None, rowcount=0):
        self.rows = rows
        self.one = one
        self.rowcount = rowcount

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


class Connection:
    def __init__(self, *, rows=(), updated=True):
        self.rows = rows
        self.updated = updated
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "UPDATE auth_sessions" in query:
            return Result(one=(UUID(TARGET),) if self.updated else None, rowcount=1 if self.updated else 0)
        if "SELECT id, created_at, last_seen_at, expires_at" in query:
            return Result(rows=self.rows)
        return Result()


class Database:
    def __init__(self, connection):
        self.connection = connection
        self.context = None

    @contextmanager
    def tenant_transaction(self, **kwargs):
        self.context = kwargs
        yield self.connection


def test_list_sessions_is_scoped_to_revalidated_current_identity():
    now = datetime.now(UTC)
    row = (UUID(TARGET), now, now, now + timedelta(days=2), None, "Android")
    database = Database(Connection(rows=[row]))
    service = SessionService(database)

    result = service.list_sessions(
        tenant_id=TENANT,
        subject_id=SUBJECT,
        current_session_id=CURRENT,
        session_token_hash=TOKEN_HASH,
        expected_role="owner_admin",
        expected_branch_ids=frozenset(),
    )

    assert result == [{
        "id": TARGET,
        "created_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=2)).isoformat(),
        "revoked": False,
        "device_label": "Android",
        "current": False,
    }]
    assert database.context == {
        "tenant_id": TENANT,
        "subject_id": SUBJECT,
        "expected_role": "owner_admin",
        "expected_branch_ids": frozenset(),
        "session_id": CURRENT,
        "session_token_hash": TOKEN_HASH,
    }
    query, params = database.connection.calls[0]
    assert "identity_id = %s" in query
    assert params == (TENANT, SUBJECT)


def test_selected_session_revocation_is_subject_scoped_and_audited():
    database = Database(Connection(updated=True))
    service = SessionService(database)

    assert service.revoke_session(
        tenant_id=TENANT,
        subject_id=SUBJECT,
        current_session_id=CURRENT,
        session_token_hash=TOKEN_HASH,
        expected_role="owner_admin",
        expected_branch_ids=frozenset(),
        target_session_id=TARGET,
    )
    assert database.context["session_id"] == CURRENT
    update_query, update_params = database.connection.calls[0]
    assert "tenant_id = %s AND identity_id = %s" in update_query
    assert update_params == (TARGET, TENANT, SUBJECT)
    assert any("security_audit_events" in query for query, _ in database.connection.calls)


def test_selected_session_revocation_returns_false_for_missing_or_already_revoked():
    database = Database(Connection(updated=False))
    service = SessionService(database)

    assert not service.revoke_session(
        tenant_id=TENANT,
        subject_id=SUBJECT,
        current_session_id=CURRENT,
        session_token_hash=TOKEN_HASH,
        expected_role="owner_admin",
        expected_branch_ids=frozenset(),
        target_session_id=TARGET,
    )
    assert len(database.connection.calls) == 1



def _session_api_client(database):
    context = AccessContext(
        subject_id=SUBJECT,
        tenant_id=TENANT,
        role=Role.OWNER_ADMIN,
        session_id=CURRENT,
        session_token_hash=TOKEN_HASH,
    )
    app = FastAPI()
    app.include_router(
        create_session_router(database, context_dependency=lambda: context)
    )
    return TestClient(app)


def test_session_inventory_http_route_returns_only_service_scoped_rows():
    now = datetime.now(UTC)
    database = Database(
        Connection(rows=[(
            UUID(TARGET), now, now, now + timedelta(days=1), None, "Android"
        )])
    )
    response = _session_api_client(database).get("/api/v1/auth/sessions")

    assert response.status_code == 200
    assert response.json()[0]["id"] == TARGET
    assert response.json()[0]["device_label"] == "Android"
    assert database.context["subject_id"] == SUBJECT


def test_selected_session_http_revocation_requires_same_origin_and_audits():
    database = Database(Connection(updated=True))
    client = _session_api_client(database)

    denied = client.delete(f"/api/v1/auth/sessions/{TARGET}")
    assert denied.status_code == 403
    assert database.connection.calls == []

    response = client.delete(
        f"/api/v1/auth/sessions/{TARGET}",
        headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 204
    assert database.context["subject_id"] == SUBJECT
    assert any(
        "security_audit_events" in query
        for query, _ in database.connection.calls
    )
