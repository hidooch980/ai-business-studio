# ERP Completion Roadmap

## Purpose

This roadmap defines the order for completing the modular ERP without treating catalog metadata, a passing lint check, or a preview response as proof that a business workflow is production-ready.

## Delivery principles

- Complete one end-to-end business cycle at a time.
- Preserve tenant isolation at API, query, database-constraint, event, and reporting layers.
- Use integer minor units for money and explicit currency codes; never use floating-point money.
- Keep inventory movements and posted financial journals immutable; correct them with compensating transactions.
- Make every externally retried write idempotent and bind idempotency keys to canonical request hashes.
- Require explicit authorization and approval for financial commitments, posting, refunds, and payment execution.
- Use the transactional outbox for events that must be delivered after a committed transaction.
- Keep AI recommendations advisory until a user with the correct permission approves the action.
- A module is not production-ready until migrations, API contracts, permissions, audit, observability, and automated tests are complete.

## Ordered delivery stages

### 0. Foundation stabilization

- Resolve lint, type, migration, dependency, and test failures.
- Test clean install, upgrade from the previous supported schema, and downgrade where safe.
- Run integration tests against SQLite and PostgreSQL where supported.
- Add tenant-isolation, authorization-denial, duplicate-request, rollback, and concurrent-write tests.
- Pin and audit dependencies; build the production container; validate backup and restore procedures.

**Exit criteria:** all required CI jobs pass on the exact candidate commit; migration upgrade is repeatable; no unresolved critical/high security findings.

### 1. Purchase-to-stock hardening

- Supplier lifecycle, contact validation, payment terms, and duplicate supplier controls.
- Purchase order draft, approval, cancellation, partial receiving, over-receipt prevention, and receiving discrepancy records.
- Receipt idempotency, immutable stock movements, audit trail, and transactional outbox.
- Add concurrency tests for simultaneous receipts and duplicate idempotency keys.
- Add supplier scorecards for delivery reliability, accepted quality, price variance, and lead-time variance.

**Exit criteria:** end-to-end supplier-to-stock tests pass on PostgreSQL; no duplicate stock on retries or concurrent receipt attempts.

### 2. Purchase-to-pay

- Supplier invoice capture and document attachment metadata.
- Two-way/three-way matching between purchase order, goods receipt, and supplier invoice.
- Price/quantity variance tolerances with configurable approval escalation.
- Accounts-payable ledger, due dates, credit notes, debit notes, payment batches, and payment status tracking.
- Tax treatment and currency-aware invoice totals.
- Payment provider/bank integration only behind explicit tenant configuration and approval.

**Exit criteria:** invoice cannot be posted twice; mismatches are blocked or escalated; AP balances reconcile to the general ledger.

### 3. Sales-to-cash and POS

- Product pricing, price lists, discounts, promotions, quotes, and sales orders.
- POS checkout with cash, card-terminal, and online payment references.
- Stock reservation and issue, partial fulfillment, exchanges, returns, refunds, and credit notes.
- Cash drawer sessions, opening/closing counts, cashier variance, and shift handover.
- Offline-safe transaction queue with conflict resolution and idempotent synchronization.

**Exit criteria:** sale, payment, stock issue, return, refund, and accounting reversal are traceable and reconcile.

### 4. Inventory intelligence

- Multi-warehouse transfers, reservations, cycle counts, stock adjustments, and approval.
- Lot/batch, serial number, expiry date, recall traceability, and FEFO/FIFO policies where applicable.
- Inventory valuation methods, landed-cost allocation, and negative-stock policy.
- Reorder forecasts, supplier comparison, safety stock, and human-approved replenishment.
- Alerts for expiry, slow-moving inventory, stockout risk, and abnormal shrinkage.

**Exit criteria:** on-hand, reserved, available, and valued stock reconcile to the movement ledger.

### 5. Accounting and finance integration

- Configurable chart of accounts and posting rules per tenant.
- Automatic journals for purchasing, inventory, sales, COGS, tax, payroll, refunds, and payment fees.
- Period close, accruals, reversals, adjustments, and locked-period controls.
- Bank statement import, matching, reconciliation, and payment settlement.
- Multi-currency revaluation and realized/unrealized FX where enabled.
- Trial balance, general ledger, P&L, balance sheet, cash flow, and tax reports.

**Exit criteria:** every source transaction maps to balanced journal entries; subledgers reconcile; closed periods cannot be mutated.

### 6. People, governance, and operations

- Employee records, roles, shifts, attendance, leave, payroll inputs, and payslip workflow.
- Approval matrix by amount, department, location, and transaction type.
- Budgets, cost centers, purchase limits, and variance alerts.
- Notification templates, delivery retries, dead-letter handling, and delivery audit.
- Centralized logs, metrics, tracing, health checks, backup monitoring, and restore drills.
- Data export, retention controls, privacy requests, and tenant offboarding.

**Exit criteria:** sensitive actions are permissioned, approved, audited, monitored, and recoverable.

### 7. AI and management intelligence

- Forecast demand, cash flow, supplier risk, staffing requirements, and sales trends.
- Explain recommendations with source data, confidence, freshness, and expected impact.
- Detect anomalies such as unusual refunds, duplicate invoices, stock shrinkage, and margin changes.
- Compare branches, products, suppliers, and channels with drill-down to source transactions.
- Keep model versions, feature provenance, evaluation metrics, and human feedback auditable.

**Exit criteria:** AI suggestions are measurable and explainable; no autonomous financial execution without an explicit, separately approved policy.

### 8. Product editions, integrations, and release

- Maintain independent semantic versions for the product, API, and modules.
- Enforce module dependencies, tenant entitlements, feature flags, and RBAC at runtime.
- Publish stable API contracts, webhooks, SDK examples, and integration test suites.
- Provide Persian, English, Arabic, and Turkish localization, timezone-aware dates, and configurable fiscal calendars.
- Complete accessibility, responsive mobile/PWA, security review, load tests, migration rehearsal, and release rollback.
- Ship signed, reproducible artifacts with release notes and a documented support policy.

**Exit criteria:** release candidate passes full CI, security review, migration rehearsal, restore drill, and end-to-end business-cycle tests.

## New high-value recommendations

1. **Three-way invoice matching:** prevent overbilling by matching PO, receipt, and invoice before AP posting.
2. **Supplier reliability score:** combine delivery punctuality, quality acceptance, price stability, and dispute history.
3. **Approval matrix and budget guardrails:** route high-value or out-of-budget purchases to the correct approver.
4. **Lot/expiry and recall traceability:** essential for food, pharmacy, cosmetics, and other perishable/regulated inventory.
5. **Cashier shift reconciliation:** reconcile cash drawer, card-terminal totals, online settlements, refunds, and variances.
6. **Subledger-to-GL reconciliation:** continuously detect gaps between inventory, receivables, payables, payroll, and accounting.
7. **AI anomaly detection with evidence:** surface suspicious transactions with traceable reasons, never silently mutate records.
8. **Backup restore drills and release rollback:** measure recovery time and prove that backups are usable.
9. **Offline-first branch operations:** queue sales safely and reconcile conflicts without duplicating payments or stock movements.
10. **Tenant data lifecycle controls:** export, retention, deletion workflows, and verifiable tenant separation.

## Release rule

A feature may be described as implemented only when its code exists. It may be described as tested only when the relevant automated tests pass on the current commit. It may be described as released only after merge, migration, deployment, and post-deployment checks are verified.
