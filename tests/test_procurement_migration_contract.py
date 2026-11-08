from pathlib import Path

INFRA = Path("migrations/0002_transactional_infrastructure.sql").read_text(encoding="utf-8").lower()
PROCUREMENT = Path("migrations/0003_suppliers_purchase_orders.sql").read_text(encoding="utf-8").lower()
PAYMENT = Path("migrations/0004_receipts_invoices_payments.sql").read_text(encoding="utf-8").lower()


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


def test_purchase_to_payment_migration_enforces_rls_and_three_way_relationships():
    tables = (
        "goods_receipts", "goods_receipt_lines", "inventory_movements", "supplier_invoices",
        "supplier_invoice_lines", "accounts_payable", "supplier_payments",
        "payment_allocations", "financial_ledger_entries",
    )
    for table in tables:
        assert f"create table {table}" in PAYMENT
    assert_tenant_rls_is_applied(PAYMENT, tables)
    assert "foreign key (tenant_id, goods_receipt_line_id, purchase_order_id, po_line_number)" in PAYMENT
    assert "references goods_receipt_lines(tenant_id, id, purchase_order_id, po_line_number)" in PAYMENT
    assert "unique (tenant_id, payment_reference)" in PAYMENT
    assert "inventory_movements_append_only" in PAYMENT
    assert "payment_allocations_append_only" in PAYMENT
    assert "financial_ledger_entries_append_only" in PAYMENT
    assert "create constraint trigger financial_journal_balanced" in PAYMENT
    assert "deferrable initially deferred" in PAYMENT
    assert "ensure_journal_balanced" in PAYMENT
    assert "invoice_total_minor bigint not null check (invoice_total_minor > 0)" in PAYMENT
