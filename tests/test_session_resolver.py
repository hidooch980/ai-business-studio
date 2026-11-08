from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from starlette.requests import Request

from retail_app.infrastructure.database import PostgresDatabase
from retail_app.security.session_resolver import SessionResolver

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
RUNTIME_URL = "postgresql://retail_session_runtime:session-runtime-test-only@localhost:5432/retail_test"


@pytest.fixture(scope="module", autouse=True)
def restricted_runtime_role():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            """
            DO $role$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'retail_session_runtime') THEN
                    CREATE ROLE retail_session_runtime LOGIN PASSWORD 'session-runtime-test-only'
                        NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
                END IF;
            END
            $role$
            """
        )
        conn.execute("GRANT USAGE ON SCHEMA public TO retail_session_runtime")
        conn.execute(
            """
            GRANT SELECT ON identities, tenants, tenant_memberships,
                branch_memberships, branches TO retail_session_runtime
            """
        )
        conn.execute(
            "GRANT EXECUTE ON FUNCTION public.resolve_auth_session(bytea) TO retail_session_runtime"
        )
        conn.execute("REVOKE ALL ON auth_sessions FROM retail_session_runtime")
        assert conn.execute(
            "SELECT rolbypassrls FROM pg_roles WHERE rolname = 'retail_session_runtime'"
        ).fetchone() == (False,)
    yield


@pytest.fixture
def auth_records():
    tenant_id, branch_one, branch_two, subject_id, session_id = [uuid4() for _ in range(5)]
    token = f"test-session-{uuid4().hex}-{uuid4().hex}"
    token_hash = hashlib.sha256(token.encode()).digest()
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("INSERT INTO tenants (id, name) VALUES (%s, 'Resolver tenant')", (tenant_id,))
        conn.execute(
            "INSERT INTO branches (id, tenant_id, name) VALUES (%s, %s, 'Assigned'), (%s, %s, 'Unassigned')",
            (branch_one, tenant_id, branch_two, tenant_id),
        )
        conn.execute(
            "INSERT INTO identities (id, account_type, phone_e164) VALUES (%s, 'workforce', %s)",
            (subject_id, f"+1555{str(uuid4().int)[:7]}"),
        )
        conn.execute(
            "INSERT INTO tenant_memberships (tenant_id, identity_id, role) VALUES (%s, %s, 'branch_manager')",
            (tenant_id, subject_id),
        )
        conn.execute(
            "INSERT INTO branch_memberships (tenant_id, branch_id, identity_id) VALUES (%s, %s, %s)",
            (tenant_id, branch_one, subject_id),
        )
        conn.execute(
            """
            INSERT INTO auth_sessions
                (id, tenant_id, identity_id, refresh_token_hash, expires_at)
            VALUES (%s, %s, %s, %s, now() + interval '1 hour')
            """,
            (session_id, tenant_id, subject_id, token_hash),
        )
    return {
        "tenant_id": tenant_id,
        "branch_one": branch_one,
        "branch_two": branch_two,
        "subject_id": subject_id,
        "session_id": session_id,
        "token": token,
        "token_hash": token_hash,
    }


def _request(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/procurement/purchase-orders",
            "headers": [
                (b"cookie", f"__Host-retail_session={token}".encode()),
                (b"x-role", b"owner_admin"),
                (b"x-tenant-id", b"attacker-tenant"),
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "scheme": "https",
        }
    )


def test_database_resolver_uses_database_role_and_branch_memberships(auth_records):
    from retail_app.security.authorization import Role

    database = PostgresDatabase(RUNTIME_URL)
    context = SessionResolver(database)(_request(auth_records["token"]))

    assert context.subject_id == str(auth_records["subject_id"])
    assert context.tenant_id == str(auth_records["tenant_id"])
    assert context.role is Role.BRANCH_MANAGER
    assert context.branch_ids == frozenset({str(auth_records["branch_one"])})
    assert str(auth_records["branch_two"]) not in context.branch_ids


def test_runtime_can_resolve_hash_but_cannot_read_session_table(auth_records):
    with psycopg.connect(RUNTIME_URL) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT id FROM auth_sessions").fetchall()
        row = conn.execute(
            "SELECT session_id, tenant_id, identity_id FROM public.resolve_auth_session(%s)",
            (auth_records["token_hash"],),
        ).fetchone()
    assert row == (
        auth_records["session_id"],
        auth_records["tenant_id"],
        auth_records["subject_id"],
    )


@pytest.mark.parametrize("mutation", ["expired", "revoked"])
def test_expired_and_revoked_sessions_are_rejected(auth_records, mutation):
    from fastapi import HTTPException

    with psycopg.connect(DATABASE_URL) as conn:
        if mutation == "expired":
            conn.execute(
                "UPDATE auth_sessions SET expires_at = now() - interval '1 minute' WHERE id = %s",
                (auth_records["session_id"],),
            )
        else:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at = now() WHERE id = %s",
                (auth_records["session_id"],),
            )

    with pytest.raises(HTTPException) as error:
        SessionResolver(PostgresDatabase(RUNTIME_URL))(_request(auth_records["token"]))
    assert error.value.status_code == 401


def test_revoked_membership_is_rejected_immediately(auth_records):
    from fastapi import HTTPException

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE tenant_memberships SET status = 'revoked' WHERE tenant_id = %s AND identity_id = %s",
            (auth_records["tenant_id"], auth_records["subject_id"]),
        )

    with pytest.raises(HTTPException) as error:
        SessionResolver(PostgresDatabase(RUNTIME_URL))(_request(auth_records["token"]))
    assert error.value.status_code == 401


def test_role_changes_are_loaded_from_database_not_client_headers(auth_records):
    from retail_app.security.authorization import Role

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE tenant_memberships SET role = 'employee' WHERE tenant_id = %s AND identity_id = %s",
            (auth_records["tenant_id"], auth_records["subject_id"]),
        )

    context = SessionResolver(PostgresDatabase(RUNTIME_URL))(_request(auth_records["token"]))
    assert context.role is Role.EMPLOYEE
    assert context.role is not Role.OWNER_ADMIN


def test_inactive_identity_is_rejected(auth_records):
    from fastapi import HTTPException

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE identities SET is_active = false WHERE id = %s",
            (auth_records["subject_id"],),
        )

    with pytest.raises(HTTPException) as error:
        SessionResolver(PostgresDatabase(RUNTIME_URL))(_request(auth_records["token"]))
    assert error.value.status_code == 401


def test_unknown_token_is_rejected_without_disclosing_session_data():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        SessionResolver(PostgresDatabase(RUNTIME_URL))(_request("x" * 48))
    assert error.value.status_code == 401


def test_resolver_clock_must_be_timezone_aware(auth_records):
    with pytest.raises(ValueError, match="timezone-aware"):
        SessionResolver(
            PostgresDatabase(RUNTIME_URL),
            clock=lambda: datetime.now().replace(tzinfo=None),
        )(_request(auth_records["token"]))
