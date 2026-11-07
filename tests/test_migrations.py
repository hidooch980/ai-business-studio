import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError


def test_alembic_upgrade_and_downgrade_on_sqlite(tmp_path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, f"alembic upgrade failed:\\n{upgrade.stdout}\\n{upgrade.stderr}"
    engine = create_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0006_financial_ledger"
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                    (id, tenant_id, actor_user_id, action, resource_type, resource_id, outcome, request_id, created_at)
                    VALUES (:id, NULL, NULL, 'test.created', 'test', '1', 'success', NULL, '2026-01-01 00:00:00')
                    """
                ),
                {"id": uuid4().hex},
            )
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(text("UPDATE audit_events SET outcome = 'tampered'"))
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(text("DELETE FROM audit_events"))
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == 1
        assert "csrf_token_hash" in {column["name"] for column in inspect(engine).get_columns("user_sessions")}
        assert "uq_tenant_invitations_pending_email" in {index["name"] for index in inspect(engine).get_indexes("tenant_invitations")}
        assert {
            "alembic_version",
            "tenants",
            "users",
            "memberships",
            "roles",
            "permissions",
            "role_permissions",
            "membership_roles",
            "user_sessions",
            "audit_events",
            "login_rate_limits",
            "tenant_invitations",
            "journal_entries",
            "journal_lines",
        }.issubset(tables)
        assert "ck_journal_line_one_sided" in {
            item["name"] for item in inspect(engine).get_check_constraints("journal_lines")
        }
        tenant_id = uuid4().hex
        user_id = uuid4().hex
        entry_id = uuid4().hex
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tenants (id, name, slug, is_active, created_at) VALUES (:id, 'Ledger test', 'ledger-test', 1, '2026-01-01 00:00:00')"),
                {"id": tenant_id},
            )
            connection.execute(
                text("INSERT INTO users (id, email, password_hash, display_name, is_active, is_platform_admin, created_at) VALUES (:id, 'ledger@example.test', 'hash', 'Ledger', 1, 0, '2026-01-01 00:00:00')"),
                {"id": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO journal_entries (id, tenant_id, idempotency_key, request_hash, currency, description, debit_total_minor, credit_total_minor, created_by_user_id, created_at) "
                    "VALUES (:id, :tenant, 'migration-ledger', :hash, 'USD', 'Migration test', 100, 100, :user, '2026-01-01 00:00:00')"
                ),
                {"id": entry_id, "tenant": tenant_id, "hash": "0" * 64, "user": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO journal_lines (id, tenant_id, journal_entry_id, line_number, account_code, debit_minor, credit_minor) "
                    "VALUES (:id, :tenant, :entry, 1, 'cash', 100, 0)"
                ),
                {"id": uuid4().hex, "tenant": tenant_id, "entry": entry_id},
            )
            connection.execute(
                text(
                    "INSERT INTO journal_lines (id, tenant_id, journal_entry_id, line_number, account_code, debit_minor, credit_minor) "
                    "VALUES (:id, :tenant, :entry, 2, 'income', 0, 100)"
                ),
                {"id": uuid4().hex, "tenant": tenant_id, "entry": entry_id},
            )
        with pytest.raises(DBAPIError, match="totals cannot be exceeded"):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO journal_lines (id, tenant_id, journal_entry_id, line_number, account_code, debit_minor, credit_minor) "
                        "VALUES (:id, :tenant, :entry, 3, 'cash', 1, 0)"
                    ),
                    {"id": uuid4().hex, "tenant": tenant_id, "entry": entry_id},
                )
    finally:
        engine.dispose()

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, f"alembic downgrade failed:\\n{downgrade.stdout}\\n{downgrade.stderr}"
    engine = create_engine(database_url)
    try:
        assert not (tables - {"alembic_version"}).intersection(inspect(engine).get_table_names())
    finally:
        engine.dispose()
