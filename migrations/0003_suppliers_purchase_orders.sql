-- Supplier and purchase-order foundation. Goods receipt is a later dependency.
BEGIN;

CREATE TABLE suppliers (
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    id uuid NOT NULL,
    legal_name text NOT NULL CHECK (length(btrim(legal_name)) BETWEEN 1 AND 200),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'blocked')),
    tax_identifier text,
    phone text,
    email text,
    address text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    CHECK (tax_identifier IS NULL OR length(tax_identifier) <= 64),
    CHECK (email IS NULL OR (length(email) <= 254 AND position('@' IN email) > 1))
);
CREATE INDEX suppliers_tenant_name_idx ON suppliers(tenant_id, legal_name);

CREATE TABLE purchase_orders (
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    id uuid NOT NULL,
    branch_id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    order_number text NOT NULL CHECK (length(btrim(order_number)) BETWEEN 1 AND 64),
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'partially_received', 'received', 'cancelled')),
    order_date date NOT NULL,
    expected_date date,
    notes text,
    created_by uuid NOT NULL REFERENCES identities(id),
    approved_by uuid REFERENCES identities(id),
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, branch_id, order_number),
    FOREIGN KEY (tenant_id, branch_id) REFERENCES branches(tenant_id, id),
    FOREIGN KEY (tenant_id, supplier_id) REFERENCES suppliers(tenant_id, id),
    CHECK (expected_date IS NULL OR expected_date >= order_date),
    CHECK ((status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
        OR status <> 'approved')
);
CREATE INDEX purchase_orders_supplier_idx ON purchase_orders(tenant_id, supplier_id, order_date DESC);
CREATE INDEX purchase_orders_branch_status_idx ON purchase_orders(tenant_id, branch_id, status, order_date DESC);

CREATE TABLE purchase_order_lines (
    tenant_id uuid NOT NULL,
    purchase_order_id uuid NOT NULL,
    line_number integer NOT NULL CHECK (line_number > 0),
    item_id uuid NOT NULL,
    description text NOT NULL CHECK (length(btrim(description)) BETWEEN 1 AND 500),
    quantity_milli bigint NOT NULL CHECK (quantity_milli > 0),
    unit_price_minor bigint NOT NULL CHECK (unit_price_minor >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, purchase_order_id, line_number),
    FOREIGN KEY (tenant_id, purchase_order_id) REFERENCES purchase_orders(tenant_id, id)
);
CREATE INDEX purchase_order_lines_item_idx ON purchase_order_lines(tenant_id, item_id);

DO $migration$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['suppliers', 'purchase_orders', 'purchase_order_lines'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), '''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'', true), '''')::uuid)',
            table_name
        );
    END LOOP;
END
$migration$;

COMMIT;
