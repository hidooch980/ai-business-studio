-- Purchase receipt, supplier invoice matching, accounts payable and payment chain.
BEGIN;

CREATE TABLE goods_receipts (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    branch_id uuid NOT NULL,
    purchase_order_id uuid NOT NULL,
    receipt_number text NOT NULL CHECK (length(btrim(receipt_number)) BETWEEN 1 AND 64),
    received_at timestamptz NOT NULL DEFAULT now(),
    received_by uuid NOT NULL REFERENCES identities(id),
    notes text,
    status text NOT NULL DEFAULT 'posted' CHECK (status IN ('posted', 'void')),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, branch_id, receipt_number),
    UNIQUE (tenant_id, id, purchase_order_id),
    FOREIGN KEY (tenant_id, branch_id) REFERENCES branches(tenant_id, id),
    FOREIGN KEY (tenant_id, purchase_order_id) REFERENCES purchase_orders(tenant_id, id)
);
CREATE INDEX goods_receipts_po_idx ON goods_receipts(tenant_id, purchase_order_id, received_at);

CREATE TABLE goods_receipt_lines (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    goods_receipt_id uuid NOT NULL,
    purchase_order_id uuid NOT NULL,
    po_line_number integer NOT NULL,
    received_quantity_milli bigint NOT NULL CHECK (received_quantity_milli > 0),
    accepted_quantity_milli bigint NOT NULL CHECK (accepted_quantity_milli >= 0),
    rejected_quantity_milli bigint NOT NULL CHECK (rejected_quantity_milli >= 0),
    discrepancy_code text CHECK (discrepancy_code IN ('shortage', 'overdelivery', 'damaged', 'wrong_item', 'quality', 'other')),
    discrepancy_note text,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, goods_receipt_id, po_line_number),
    UNIQUE (tenant_id, id, purchase_order_id, po_line_number),
    FOREIGN KEY (tenant_id, goods_receipt_id, purchase_order_id)
        REFERENCES goods_receipts(tenant_id, id, purchase_order_id),
    FOREIGN KEY (tenant_id, purchase_order_id, po_line_number)
        REFERENCES purchase_order_lines(tenant_id, purchase_order_id, line_number),
    CHECK (received_quantity_milli = accepted_quantity_milli + rejected_quantity_milli),
    CHECK ((discrepancy_code IS NULL AND received_quantity_milli = accepted_quantity_milli)
        OR discrepancy_code IS NOT NULL)
);
CREATE INDEX goods_receipt_lines_po_line_idx
    ON goods_receipt_lines(tenant_id, purchase_order_id, po_line_number);

CREATE TABLE inventory_movements (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    branch_id uuid NOT NULL,
    item_id uuid NOT NULL,
    movement_type text NOT NULL CHECK (movement_type IN ('purchase_receipt', 'issue', 'return', 'adjustment')),
    quantity_milli bigint NOT NULL CHECK (quantity_milli <> 0),
    source_type text NOT NULL,
    source_id uuid NOT NULL,
    source_line_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES identities(id),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, source_type, source_line_id),
    CHECK (movement_type <> 'purchase_receipt' OR quantity_milli > 0),
    CHECK (movement_type <> 'issue' OR quantity_milli < 0),
    CHECK (movement_type <> 'return' OR quantity_milli > 0),
    FOREIGN KEY (tenant_id, branch_id) REFERENCES branches(tenant_id, id)
);
CREATE INDEX inventory_movements_balance_idx
    ON inventory_movements(tenant_id, branch_id, item_id, occurred_at);
CREATE INDEX inventory_movements_source_idx
    ON inventory_movements(tenant_id, source_type, source_id);

CREATE TABLE supplier_invoices (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    purchase_order_id uuid NOT NULL,
    invoice_number text NOT NULL CHECK (length(btrim(invoice_number)) BETWEEN 1 AND 100),
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    invoice_date date NOT NULL,
    due_date date NOT NULL,
    invoice_total_minor bigint NOT NULL CHECK (invoice_total_minor > 0),
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'matched', 'disputed', 'void')),
    created_by uuid NOT NULL REFERENCES identities(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    matched_at timestamptz,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, supplier_id, invoice_number),
    UNIQUE (tenant_id, id, purchase_order_id),
    FOREIGN KEY (tenant_id, supplier_id) REFERENCES suppliers(tenant_id, id),
    FOREIGN KEY (tenant_id, purchase_order_id) REFERENCES purchase_orders(tenant_id, id),
    CHECK (due_date >= invoice_date),
    CHECK ((status = 'matched' AND matched_at IS NOT NULL) OR status <> 'matched')
);
CREATE INDEX supplier_invoices_due_idx
    ON supplier_invoices(tenant_id, due_date) WHERE status = 'matched';

CREATE TABLE supplier_invoice_lines (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    purchase_order_id uuid NOT NULL,
    po_line_number integer NOT NULL,
    goods_receipt_line_id uuid NOT NULL,
    quantity_milli bigint NOT NULL CHECK (quantity_milli > 0),
    unit_price_minor bigint NOT NULL CHECK (unit_price_minor >= 0),
    line_total_minor bigint NOT NULL CHECK (line_total_minor >= 0),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, invoice_id, po_line_number, goods_receipt_line_id),
    FOREIGN KEY (tenant_id, invoice_id, purchase_order_id)
        REFERENCES supplier_invoices(tenant_id, id, purchase_order_id),
    FOREIGN KEY (tenant_id, purchase_order_id, po_line_number)
        REFERENCES purchase_order_lines(tenant_id, purchase_order_id, line_number),
    FOREIGN KEY (tenant_id, goods_receipt_line_id, purchase_order_id, po_line_number)
        REFERENCES goods_receipt_lines(tenant_id, id, purchase_order_id, po_line_number)
);

CREATE TABLE accounts_payable (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    original_amount_minor bigint NOT NULL CHECK (original_amount_minor >= 0),
    outstanding_amount_minor bigint NOT NULL CHECK (outstanding_amount_minor >= 0),
    due_date date NOT NULL,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'partially_paid', 'paid', 'void')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, invoice_id),
    FOREIGN KEY (tenant_id, invoice_id) REFERENCES supplier_invoices(tenant_id, id),
    FOREIGN KEY (tenant_id, supplier_id) REFERENCES suppliers(tenant_id, id),
    CHECK (outstanding_amount_minor <= original_amount_minor),
    CHECK ((status = 'paid' AND outstanding_amount_minor = 0)
        OR (status <> 'paid' AND outstanding_amount_minor > 0)
        OR (status = 'void' AND outstanding_amount_minor = 0))
);
CREATE INDEX accounts_payable_due_idx
    ON accounts_payable(tenant_id, due_date) WHERE status IN ('open', 'partially_paid');

CREATE TABLE supplier_payments (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    payment_reference text NOT NULL CHECK (length(btrim(payment_reference)) BETWEEN 1 AND 120),
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    amount_minor bigint NOT NULL CHECK (amount_minor > 0),
    paid_at timestamptz NOT NULL,
    method text NOT NULL CHECK (method IN ('bank_transfer', 'cash', 'card', 'other')),
    status text NOT NULL DEFAULT 'posted' CHECK (status IN ('posted', 'void')),
    created_by uuid NOT NULL REFERENCES identities(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, payment_reference),
    FOREIGN KEY (tenant_id, supplier_id) REFERENCES suppliers(tenant_id, id)
);

CREATE TABLE payment_allocations (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    payment_id uuid NOT NULL,
    payable_id uuid NOT NULL,
    amount_minor bigint NOT NULL CHECK (amount_minor > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, payment_id, payable_id),
    FOREIGN KEY (tenant_id, payment_id) REFERENCES supplier_payments(tenant_id, id),
    FOREIGN KEY (tenant_id, payable_id) REFERENCES accounts_payable(tenant_id, id)
);

CREATE TABLE financial_ledger_entries (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    journal_id uuid NOT NULL,
    source_type text NOT NULL,
    source_id uuid NOT NULL,
    account_code text NOT NULL,
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    debit_minor bigint NOT NULL DEFAULT 0 CHECK (debit_minor >= 0),
    credit_minor bigint NOT NULL DEFAULT 0 CHECK (credit_minor >= 0),
    posted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    CHECK ((debit_minor > 0 AND credit_minor = 0) OR (credit_minor > 0 AND debit_minor = 0))
);
CREATE INDEX financial_ledger_source_idx
    ON financial_ledger_entries(tenant_id, source_type, source_id);
CREATE INDEX financial_ledger_journal_idx
    ON financial_ledger_entries(tenant_id, journal_id);

DO $migration$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'goods_receipts', 'goods_receipt_lines', 'inventory_movements', 'supplier_invoices',
        'supplier_invoice_lines', 'accounts_payable', 'supplier_payments',
        'payment_allocations', 'financial_ledger_entries'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), '''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'', true), '''')::uuid)',
            table_name
        );
    END LOOP;
END
$migration$;

CREATE TRIGGER inventory_movements_append_only
BEFORE UPDATE OR DELETE ON inventory_movements
FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_mutation();

CREATE TRIGGER payment_allocations_append_only
BEFORE UPDATE OR DELETE ON payment_allocations
FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_mutation();

CREATE TRIGGER financial_ledger_entries_append_only
BEFORE UPDATE OR DELETE ON financial_ledger_entries
FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_mutation();

CREATE FUNCTION ensure_journal_balanced() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    debit_total bigint;
    credit_total bigint;
    currency_count integer;
BEGIN
    SELECT COALESCE(SUM(debit_minor), 0), COALESCE(SUM(credit_minor), 0),
           COUNT(DISTINCT currency)
      INTO debit_total, credit_total, currency_count
      FROM financial_ledger_entries
     WHERE tenant_id = NEW.tenant_id AND journal_id = NEW.journal_id;
    IF debit_total <= 0 OR debit_total <> credit_total OR currency_count <> 1 THEN
        RAISE EXCEPTION 'journal % is not balanced', NEW.journal_id;
    END IF;
    RETURN NULL;
END
$function$;

CREATE CONSTRAINT TRIGGER financial_journal_balanced
AFTER INSERT ON financial_ledger_entries
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION ensure_journal_balanced();

COMMIT;
