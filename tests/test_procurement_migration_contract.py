from pathlib import Path

INFRA = Path("migrations/0002_transactional_infrastructure.sql").read_text(encoding="utf-8").lower()
PROCUREMENT = Path("migrations/0003_suppliers_purchase_orders.sql").read_text(encoding="utf-8").lower()


def assert_tenant_rls_is_applied(migration: str, tables: tuple[str, ...]) -> None:
    assert "execute format('alter table %i enable row level security', table_name)" in migration
    assert "execute format('alter table %i force row level security', table_name)" in migration
    assert "create policy tenant_isolation on %i" in migration
    for table in tables:
        assert f"'{table}'" in migration


def test_infrastructure_migration_has_tenant_scoped_reliability_tables():
    tables = ("idempotency_records", "domain_events", "outbox_messages", "audit_events")
    for table in tables:
        assert f"create table {table}" in INFRA
    assert_tenant_rls_is_applied(INFRA, tables)
    assert "request_sha256 bytea" in INFRA
    assert "unique (tenant_id, operation, idempotency_key)" in INFRA
    assert "domain_events_append_only" in INFRA
    assert "audit_events_append_only" in INFRA


def test_procurement_migration_enforces_tenant_and_branch_relationships():
    tables = ("suppliers", "purchase_orders", "purchase_order_lines")
    for table in tables:
        assert f"create table {table}" in PROCUREMENT
    assert_tenant_rls_is_applied(PROCUREMENT, tables)
    assert "foreign key (tenant_id, branch_id) references branches(tenant_id, id)" in PROCUREMENT
    assert "foreign key (tenant_id, supplier_id) references suppliers(tenant_id, id)" in PROCUREMENT
    assert "unit_price_minor bigint not null check (unit_price_minor >= 0)" in PROCUREMENT
