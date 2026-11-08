from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0001_identity_security.sql"
RUNTIME_URL = "postgresql://retail_runtime:runtime-test-only@localhost:5432/retail_test"

TENANT_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
TENANT_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
BRANCH_A = UUID("aaaaaaaa-0001-4000-8000-000000000001")
BRANCH_B = UUID("bbbbbbbb-0001-4000-8000-000000000001")
USER_A = UUID("aaaaaaaa-1001-4000-8000-000000000001")
USER_A2 = UUID("aaaaaaaa-1002-4000-8000-000000000002")
USER_B = UUID("bbbbbbbb-1001-4000-8000-000000000001")
SESSION_A = UUID("aaaaaaaa-2001-4000-8000-000000000001")
SESSION_A2 = UUID("aaaaaaaa-2002-4000-8000-000000000002")
SESSION_B = UUID("bbbbbbbb-2001-4000-8000-000000000001")
OTP_ANON = UUID("cccccccc-3001-4000-8000-000000000001")


@pytest.fixture(scope="session", autouse=True)
def postgres_schema():
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "CREATE ROLE retail_runtime LOGIN PASSWORD 'runtime-test-only' "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
        conn.execute("GRANT USAGE ON SCHEMA public TO retail_runtime")
        conn.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO retail_runtime"
        )
        conn.execute(
            """
            INSERT INTO tenants (id, name) VALUES (%s, 'Tenant A'), (%s, 'Tenant B');
            """,
            (TENANT_A, TENANT_B),
        )
        conn.execute(
            """
            INSERT INTO branches (id, tenant_id, name) VALUES
                (%s, %s, 'A Main'), (%s, %s, 'B Main');
            """,
            (BRANCH_A, TENANT_A, BRANCH_B, TENANT_B),
        )
        conn.execute(
            """
            INSERT INTO identities (id, account_type, phone_e164) VALUES
                (%s, 'workforce', '+12025550101'),
                (%s, 'customer', '+12025550102'),
                (%s, 'workforce', '+12025550103');
            """,
            (USER_A, USER_A2, USER_B),
        )
        conn.execute(
            """
            INSERT INTO tenant_memberships (tenant_id, identity_id, role) VALUES
                (%s, %s, 'owner_admin'), (%s, %s, 'customer'), (%s, %s, 'owner_admin');
            """,
            (TENANT_A, USER_A, TENANT_A, USER_A2, TENANT_B, USER_B),
        )
        conn.execute(
            """
            INSERT INTO branch_memberships (tenant_id, branch_id, identity_id) VALUES
                (%s, %s, %s), (%s, %s, %s);
            """,
            (TENANT_A, BRANCH_A, USER_A, TENANT_B, BRANCH_B, USER_B),
        )
        conn.execute(
            """
            INSERT INTO auth_sessions
                (id, tenant_id, identity_id, refresh_token_hash, expires_at)
            VALUES
                (%s, %s, %s, decode(repeat('01', 32), 'hex'), now() + interval '1 day'),
                (%s, %s, %s, decode(repeat('02', 32), 'hex'), now() + interval '1 day'),
                (%s, %s, %s, decode(repeat('03', 32), 'hex'), now() + interval '1 day');
            """,
            (
                SESSION_A, TENANT_A, USER_A,
                SESSION_A2, TENANT_A, USER_A2,
                SESSION_B, TENANT_B, USER_B,
            ),
        )
        conn.execute(
            """
            INSERT INTO otp_challenges
                (id, identifier_fingerprint, code_hmac, purpose, channel, expires_at, resend_after)
            VALUES (%s, decode(repeat('aa', 32), 'hex'), decode(repeat('bb', 32), 'hex'),
                    'login', 'sms', now() + interval '5 minutes', now() + interval '1 minute');
            """,
            (OTP_ANON,),
        )
    yield
    # CI uses an ephemeral database; the service is discarded after the job.


@pytest.fixture
def runtime():
    with psycopg.connect(RUNTIME_URL) as conn:
        yield conn


def set_context(conn, tenant: UUID | None = None, subject: UUID | None = None, onboarding=False):
    conn.execute(
        "SELECT set_config('app.tenant_id', %s, true)",
        (str(tenant) if tenant else "",),
    )
    conn.execute(
        "SELECT set_config('app.subject_id', %s, true)",
        (str(subject) if subject else "",),
    )
    conn.execute(
        "SELECT set_config('app.otp_onboarding', %s, true)",
        ("true" if onboarding else "false",),
    )


def test_1_migration_applies_and_forces_rls_on_all_scoped_tables():
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """
            SELECT c.relname, c.relforcerowsecurity
            FROM pg_class c
            WHERE c.relname IN (
                'tenants', 'branches', 'identities', 'tenant_memberships',
                'branch_memberships', 'auth_sessions', 'otp_challenges',
                'security_audit_events'
            )
            """
        ).fetchall()
    assert len(rows) == 8
    assert all(forced for _, forced in rows)


def test_2_missing_request_context_sees_no_tenant_data_and_cannot_insert(runtime):
    with runtime.transaction():
        set_context(runtime)
        assert runtime.execute("SELECT count(*) FROM tenants").fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege), runtime.transaction():
            runtime.execute(
                "INSERT INTO tenants (id, name) VALUES (%s, 'forbidden')",
                (UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),),
            )


def test_3_tenant_context_cannot_read_another_tenant(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        assert runtime.execute("SELECT id FROM tenants").fetchall() == [(TENANT_A,)]
        assert runtime.execute("SELECT id FROM branches").fetchall() == [(BRANCH_A,)]


def test_4_branch_membership_rows_are_tenant_scoped(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        rows = runtime.execute(
            "SELECT branch_id, identity_id FROM branch_memberships"
        ).fetchall()
        assert rows == [(BRANCH_A, USER_A)]


def test_5_sessions_are_private_to_the_authenticated_subject(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        rows = runtime.execute("SELECT id FROM auth_sessions").fetchall()
        assert rows == [(SESSION_A,)]


def test_6_identity_visibility_is_self_or_same_tenant_only(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A)
        visible = {
            row[0] for row in runtime.execute("SELECT id FROM identities").fetchall()
        }
        assert visible == {USER_A, USER_A2,}
        with pytest.raises(psycopg.errors.InsufficientPrivilege), runtime.transaction():
            runtime.execute(
                """
                INSERT INTO identities (id, account_type, phone_e164)
                VALUES (%s, 'workforce', '+12025550999')
                """,
                (UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),),
            )


def test_7_anonymous_otp_rows_require_explicit_onboarding_context(runtime):
    with runtime.transaction():
        set_context(runtime, TENANT_A, USER_A, onboarding=False)
        assert runtime.execute(
            "SELECT count(*) FROM otp_challenges WHERE tenant_id IS NULL"
        ).fetchone()[0] == 0
    with runtime.transaction():
        set_context(runtime, onboarding=True)
        assert runtime.execute(
            "SELECT id FROM otp_challenges WHERE tenant_id IS NULL"
        ).fetchall() == [(OTP_ANON,)]
        runtime.execute(
            """
            INSERT INTO otp_challenges
                (id, identifier_fingerprint, code_hmac, purpose, channel, expires_at, resend_after)
            VALUES (%s, decode(repeat('cc', 32), 'hex'), decode(repeat('dd', 32), 'hex'),
                    'login', 'sms', now() + interval '5 minutes', now() + interval '1 minute')
            """,
            (UUID("cccccccc-3002-4000-8000-000000000002"),),
        )
