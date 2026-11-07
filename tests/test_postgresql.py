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

        foreign_tenant_id = uuid4()
        foreign_account_id = uuid4()
        foreign_entry_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, is_active, created_at) "
                    "VALUES (:id, 'Foreign account tenant', :slug, true, :created_at)"
                ),
                {
                    "id": foreign_tenant_id,
                    "slug": f"pg-foreign-account-{foreign_tenant_id.hex}",
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO financial_accounts "
                    "(id, tenant_id, code, name, account_type, is_active, created_by_user_id, created_at, updated_at) "
                    "VALUES (:id, :tenant, 'FOREIGN', 'Foreign tenant account', 'asset', true, :user, :created_at, :created_at)"
                ),
                {
                    "id": foreign_account_id,
                    "tenant": foreign_tenant_id,
                    "user": user_id,
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO journal_entries "
                    "(id, tenant_id, idempotency_key, request_hash, currency, description, "
                    "debit_total_minor, credit_total_minor, created_by_user_id, created_at) "
                    "VALUES (:id, :tenant, 'pg-cross-tenant-account', :hash, 'USD', "
                    "'Cross-tenant account FK test', 100, 100, :user, :created_at)"
                ),
                {
                    "id": foreign_entry_id,
                    "tenant": tenant_id,
                    "hash": "1" * 64,
                    "user": user_id,
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            )
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO journal_lines "
                        "(id, tenant_id, journal_entry_id, line_number, account_code, financial_account_id, "
                        "debit_minor, credit_minor) "
                        "VALUES (:id, :tenant, :entry, 1, 'FOREIGN', :account, 100, 0)"
                    ),
                    {
                        "id": uuid4(),
                        "tenant": tenant_id,
                        "entry": foreign_entry_id,
                        "account": foreign_account_id,
                    },
                )

        product_id = uuid4()
        warehouse_id = uuid4()
        movement_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO products "
                    "(id, tenant_id, sku, name, unit_code, is_active, created_at, updated_at) "
                    "VALUES (:id, :tenant, 'PG-STOCK', 'Postgres stock', 'pcs', true, :created_at, :created_at)"
                ),
                {"id": product_id, "tenant": tenant_id, "created_at": "2026-01-01T00:00:00+00:00"},
            )
            connection.execute(
                text(
                    "INSERT INTO warehouses (id, tenant_id, code, name, is_active, created_at, updated_at) "
                    "VALUES (:id, :tenant, 'PG-MAIN', 'Postgres main', true, :created_at, :created_at)"
                ),
                {"id": warehouse_id, "tenant": tenant_id, "created_at": "2026-01-01T00:00:00+00:00"},
            )
            connection.execute(
                text(
                    "INSERT INTO inventory_balances "
                    "(id, tenant_id, warehouse_id, product_id, quantity_on_hand, updated_at) "
                    "VALUES (:id, :tenant, :warehouse, :product, 0, :created_at)"
                ),
                {
                    "id": uuid4(),
                    "tenant": tenant_id,
                    "warehouse": warehouse_id,
                    "product": product_id,
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO inventory_movements "
                    "(id, tenant_id, warehouse_id, product_id, movement_type, quantity_delta, "
                    "idempotency_key, request_hash, created_by_user_id, created_at) "
                    "VALUES (:id, :tenant, :warehouse, :product, 'receipt', 5, "
                    "'pg-stock-test', :hash, :user, :created_at)"
                ),
                {
                    "id": movement_id,
                    "tenant": tenant_id,
                    "warehouse": warehouse_id,
                    "product": product_id,
                    "hash": "0" * 64,
                    "user": user_id,
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            )
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT quantity_on_hand FROM inventory_balances "
                    "WHERE warehouse_id = :warehouse AND product_id = :product"
                ),
                {"warehouse": warehouse_id, "product": product_id},
            ).scalar_one() == 5
        with pytest.raises(DBAPIError, match="inventory movements are append-only"):
            with engine.begin() as connection:
                connection.execute(text("TRUNCATE TABLE inventory_movements"))
        with pytest.raises(DBAPIError, match="inventory movements are append-only"):
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE inventory_movements SET quantity_delta = 6 WHERE id = :id"),
                    {"id": movement_id},
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


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL CI service is not configured")
def test_postgresql_concurrent_owner_deactivation_preserves_last_owner() -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi import HTTPException, status
    from sqlalchemy.orm import sessionmaker

    from backend.app.identity.access_api import MembershipStatusRequest, set_membership_status
    from backend.app.identity.api_dependencies import TenantPrincipal
    from backend.app.identity.models import Membership, MembershipRole, Role, Tenant, User

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
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    tenant_id = uuid4()
    actor_user_id, first_user_id, second_user_id = uuid4(), uuid4(), uuid4()
    actor_membership_id, first_membership_id, second_membership_id = uuid4(), uuid4(), uuid4()
    owner_role_id = uuid4()

    try:
        with sessions.begin() as db:
            tenant = Tenant(id=tenant_id, name="Concurrent owner test", slug=f"owner-race-{tenant_id.hex}")
            actor = User(
                id=actor_user_id,
                email=f"{actor_user_id.hex}@example.test",
                password_hash="unused",
                display_name="Membership manager",
            )
            first_owner = User(
                id=first_user_id,
                email=f"{first_user_id.hex}@example.test",
                password_hash="unused",
                display_name="First owner",
            )
            second_owner = User(
                id=second_user_id,
                email=f"{second_user_id.hex}@example.test",
                password_hash="unused",
                display_name="Second owner",
            )
            db.add(tenant)
            db.flush()
            persisted_tenant_id = tenant.id
            assert db.get(Tenant, persisted_tenant_id) is not None
            role = Role(id=owner_role_id, tenant_id=persisted_tenant_id, name="owner", is_system=True)
            db.add_all([
                actor, first_owner, second_owner, role,
                Membership(id=actor_membership_id, tenant_id=persisted_tenant_id, user_id=actor_user_id),
                Membership(id=first_membership_id, tenant_id=persisted_tenant_id, user_id=first_user_id),
                Membership(id=second_membership_id, tenant_id=persisted_tenant_id, user_id=second_user_id),
            ])
            db.flush()
            db.add_all([
                MembershipRole(tenant_id=tenant_id, membership_id=first_membership_id, role_id=owner_role_id),
                MembershipRole(tenant_id=tenant_id, membership_id=second_membership_id, role_id=owner_role_id),
            ])

        barrier = Barrier(2)

        def deactivate(target_membership_id):
            barrier.wait(timeout=10)
            with sessions() as db:
                actor = db.get(User, actor_user_id)
                actor_membership = db.get(Membership, actor_membership_id)
                tenant = db.get(Tenant, tenant_id)
                principal = TenantPrincipal(
                    user=actor,
                    session=None,
                    membership=actor_membership,
                    tenant=tenant,
                )
                try:
                    set_membership_status(
                        target_membership_id,
                        MembershipStatusRequest(is_active=False),
                        principal,
                        None,
                        db,
                    )
                    return status.HTTP_200_OK
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(deactivate, [first_membership_id, second_membership_id]))

        assert sorted(results) == [200, 409]
        with sessions() as db:
            active_owners = db.query(Membership).join(
                MembershipRole, MembershipRole.membership_id == Membership.id
            ).filter(
                Membership.tenant_id == tenant_id,
                MembershipRole.tenant_id == tenant_id,
                MembershipRole.role_id == owner_role_id,
                Membership.is_active.is_(True),
            ).count()
            assert active_owners == 1
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
