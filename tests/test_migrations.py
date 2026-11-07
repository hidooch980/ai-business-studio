import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from backend.app.db.session import build_engine


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
    engine = build_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0013_login_rate_limit_retention"
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
        assert "ix_login_rate_limits_updated_at" in {
            item["name"] for item in inspect(engine).get_indexes("login_rate_limits")
        }
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
            "products",
            "warehouses",
            "inventory_balances",
            "inventory_movements",
            "financial_accounts",
            "outbox_events",
            "financial_periods",
        }.issubset(tables)
        assert "posting_date" in {column["name"] for column in inspect(engine).get_columns("journal_entries")}
        assert "financial_account_id" in {column["name"] for column in inspect(engine).get_columns("journal_lines")}
        assert "fk_journal_line_tenant_financial_account" in {
            item["name"] for item in inspect(engine).get_foreign_keys("journal_lines")
        }
        assert "ck_journal_line_one_sided" in {
            item["name"] for item in inspect(engine).get_check_constraints("journal_lines")
        }
        with engine.connect() as connection:
            catalog_codes = set(
                connection.execute(
                    text("SELECT code FROM permissions WHERE code IN ('catalog.read', 'catalog.write')")
                ).scalars()
            )
        assert catalog_codes == {"catalog.read", "catalog.write"}
        tenant_id = uuid4().hex
        user_id = uuid4().hex
        entry_id = uuid4().hex
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, is_active, created_at) "
                    "VALUES (:id, 'Ledger test', 'ledger-test', 1, "
                    "'2026-01-01 00:00:00')"
                ),
                {"id": tenant_id},
            )
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, display_name, "
                    "is_active, is_platform_admin, created_at) "
                    "VALUES (:id, 'ledger@example.test', 'hash', 'Ledger', 1, 0, "
                    "'2026-01-01 00:00:00')"
                ),
                {"id": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO financial_periods "
                    "(id, tenant_id, name, start_date, end_date, status, created_by_user_id, created_at, updated_at) "
                    "VALUES (:id, :tenant, 'FY-2026', '2026-01-01', '2026-12-31', 'open', :user, "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                ),
                {"id": uuid4().hex, "tenant": tenant_id, "user": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO journal_entries (id, tenant_id, idempotency_key, request_hash, currency, posting_date, description, "
                    "debit_total_minor, credit_total_minor, created_by_user_id, created_at) "
                    "VALUES (:id, :tenant, 'migration-ledger', :hash, 'USD', '2026-01-01', 'Migration test', 100, 100, :user, "
                    "'2026-01-01 00:00:00')"
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
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE journal_lines SET memo = 'tampered' WHERE journal_entry_id = :entry"),
                    {"entry": entry_id},
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

        with engine.begin() as connection:
            connection.execute(
                text("UPDATE financial_periods SET status = 'closed' WHERE tenant_id = :tenant"),
                {"tenant": tenant_id},
            )
        with pytest.raises(DBAPIError, match="open accounting period"):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO journal_entries "
                        "(id, tenant_id, idempotency_key, request_hash, currency, posting_date, description, "
                        "debit_total_minor, credit_total_minor, created_by_user_id, created_at) "
                        "VALUES (:id, :tenant, 'closed-period-direct-write', :hash, 'USD', '2026-01-01', "
                        "'Closed period test', 100, 100, :user, '2026-01-01 00:00:00')"
                    ),
                    {"id": uuid4().hex, "tenant": tenant_id, "hash": "2" * 64, "user": user_id},
                )
        product_id = uuid4().hex
        warehouse_id = uuid4().hex
        movement_id = uuid4().hex
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO products "
                    "(id, tenant_id, sku, name, unit_code, is_active, created_at, updated_at) "
                    "VALUES (:id, :tenant, 'SQL-STOCK', 'SQLite stock', 'pcs', 1, "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                ),
                {"id": product_id, "tenant": tenant_id},
            )
            connection.execute(
                text(
                    "INSERT INTO warehouses (id, tenant_id, code, name, is_active, created_at, updated_at) "
                    "VALUES (:id, :tenant, 'SQL-MAIN', 'SQLite main', 1, "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                ),
                {"id": warehouse_id, "tenant": tenant_id},
            )
            connection.execute(
                text(
                    "INSERT INTO inventory_balances "
                    "(id, tenant_id, warehouse_id, product_id, quantity_on_hand, updated_at) "
                    "VALUES (:id, :tenant, :warehouse, :product, 0, '2026-01-01 00:00:00')"
                ),
                {
                    "id": uuid4().hex,
                    "tenant": tenant_id,
                    "warehouse": warehouse_id,
                    "product": product_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO inventory_movements "
                    "(id, tenant_id, warehouse_id, product_id, movement_type, quantity_delta, "
                    "idempotency_key, request_hash, created_by_user_id, created_at) "
                    "VALUES (:id, :tenant, :warehouse, :product, 'receipt', 5, "
                    "'sqlite-stock-test', :hash, :user, '2026-01-01 00:00:00')"
                ),
                {
                    "id": movement_id,
                    "tenant": tenant_id,
                    "warehouse": warehouse_id,
                    "product": product_id,
                    "hash": "0" * 64,
                    "user": user_id,
                },
            )
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT quantity_on_hand FROM inventory_balances WHERE warehouse_id = :warehouse AND product_id = :product"),
                {"warehouse": warehouse_id, "product": product_id},
            ).scalar_one() == 5
        with pytest.raises(DBAPIError, match="inventory_movements are append-only"):
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE inventory_movements SET quantity_delta = 6 WHERE id = :id"),
                    {"id": movement_id},
                )

        foreign_tenant_id = uuid4().hex
        foreign_role_id = uuid4().hex
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, is_active, created_at) "
                    "VALUES (:id, 'Foreign tenant', :slug, 1, '2026-01-01 00:00:00')"
                ),
                {"id": foreign_tenant_id, "slug": f"foreign-{foreign_tenant_id}"},
            )
            connection.execute(
                text(
                    "INSERT INTO roles (id, tenant_id, name, description, is_system) "
                    "VALUES (:id, :tenant, 'foreign-role', NULL, 0)"
                ),
                {"id": foreign_role_id, "tenant": tenant_id},
            )
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO tenant_invitations "
                        "(id, tenant_id, email, display_name, role_id, token_hash, created_by_user_id, "
                        "expires_at, accepted_at, revoked_at, created_at) "
                        "VALUES (:id, :tenant, 'wrong-tenant@example.test', 'Wrong tenant', :role, :token, "
                        ":creator, '2027-01-01 00:00:00', NULL, NULL, '2026-01-01 00:00:00')"
                    ),
                    {
                        "id": uuid4().hex,
                        "tenant": foreign_tenant_id,
                        "role": foreign_role_id,
                        "token": uuid4().hex * 2,
                        "creator": user_id,
                    },
                )

        account_id = uuid4().hex
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO financial_accounts "
                    "(id, tenant_id, code, name, account_type, description, parent_account_id, "
                    "is_active, created_by_user_id, created_at, updated_at) "
                    "VALUES (:id, :tenant, '1000', 'Assets', 'asset', NULL, NULL, 1, :creator, "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                ),
                {"id": account_id, "tenant": tenant_id, "creator": user_id},
            )
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO financial_accounts "
                        "(id, tenant_id, code, name, account_type, description, parent_account_id, "
                        "is_active, created_by_user_id, created_at, updated_at) "
                        "VALUES (:id, :tenant, '1010', 'Foreign child', 'asset', NULL, :parent, 1, :creator, "
                        "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                    ),
                    {
                        "id": uuid4().hex,
                        "tenant": foreign_tenant_id,
                        "parent": account_id,
                        "creator": user_id,
                    },
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
    engine = build_engine(database_url)
    try:
        assert not (tables - {"alembic_version"}).intersection(inspect(engine).get_table_names())
    finally:
        engine.dispose()
