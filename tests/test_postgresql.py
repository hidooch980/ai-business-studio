import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.db.session import build_engine


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL CI service is not configured")
def test_postgresql_migrations_and_append_only_audit_trigger() -> None:
    environment = os.environ.copy()
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, f"PostgreSQL migration failed:\\n{upgrade.stdout}\\n{upgrade.stderr}"

    engine = build_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                    (id, tenant_id, actor_user_id, action, resource_type, resource_id, outcome, request_id, created_at)
                    VALUES (CAST(:id AS uuid), NULL, NULL, 'test.created', 'test', '1', 'success', NULL, :created_at)
                    """
                ),
                {"id": str(uuid4()), "created_at": "2026-01-01T00:00:00+00:00"},
            )
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(text("UPDATE audit_events SET outcome = 'tampered'"))
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(text("DELETE FROM audit_events"))
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(text("TRUNCATE TABLE audit_events"))
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == 1

        tenant_id = uuid4()
        user_id = uuid4()
        entry_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, is_active, created_at) "
                    "VALUES (:id, 'Postgres ledger test', :slug, true, :created_at)"
                ),
                {"id": tenant_id, "slug": f"pg-ledger-{tenant_id.hex}", "created_at": "2026-01-01T00:00:00+00:00"},
            )
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, display_name, is_active, is_platform_admin, created_at) "
                    "VALUES (:id, :email, 'hash', 'Ledger test', true, false, :created_at)"
                ),
                {"id": user_id, "email": f"{user_id.hex}@example.test", "created_at": "2026-01-01T00:00:00+00:00"},
            )
            connection.execute(
                text(
                    "INSERT INTO journal_entries "
                    "(id, tenant_id, idempotency_key, request_hash, currency, description, "
                    "debit_total_minor, credit_total_minor, created_by_user_id, created_at) "
                    "VALUES (:id, :tenant, 'pg-ledger-test', :hash, 'USD', 'Postgres ledger test', "
                    "100, 100, :user, :created_at)"
                ),
                {
                    "id": entry_id,
                    "tenant": tenant_id,
                    "hash": "0" * 64,
                    "user": user_id,
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO journal_lines "
                    "(id, tenant_id, journal_entry_id, line_number, account_code, debit_minor, credit_minor) "
                    "VALUES (:id, :tenant, :entry, 1, 'cash', 100, 0)"
                ),
                {"id": uuid4(), "tenant": tenant_id, "entry": entry_id},
            )
            connection.execute(
                text(
                    "INSERT INTO journal_lines "
                    "(id, tenant_id, journal_entry_id, line_number, account_code, debit_minor, credit_minor) "
                    "VALUES (:id, :tenant, :entry, 2, 'income', 0, 100)"
                ),
                {"id": uuid4(), "tenant": tenant_id, "entry": entry_id},
            )
        with pytest.raises(DBAPIError, match="totals cannot be exceeded"):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO journal_lines "
                        "(id, tenant_id, journal_entry_id, line_number, account_code, debit_minor, credit_minor) "
                        "VALUES (:id, :tenant, :entry, 3, 'cash', 1, 0)"
                    ),
                    {"id": uuid4(), "tenant": tenant_id, "entry": entry_id},
                )
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE journal_entries SET description = 'tampered' WHERE id = :id"),
                    {"id": entry_id},
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
    assert downgrade.returncode == 0, f"PostgreSQL downgrade failed:\\n{downgrade.stdout}\\n{downgrade.stderr}"
