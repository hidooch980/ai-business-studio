# Delivery Roadmap: 0–100

## Delivery policy

This roadmap is the source of truth for moving AI Business Studio from its current foundation to a verified retail ERP release. A capability is complete only when implementation, authorization, migrations, automated tests, operational documentation and acceptance evidence exist. A green CI run is necessary but does not mean a feature is merged or deployed.

## Current verified baseline

- Tenant/security and finance/inventory foundations are under dependent feature pull requests.
- Edition and tenant-module entitlement work is under review.
- Smart replenishment is advisory only; it does not create purchase orders.
- Purchase-to-stock is implemented in the purchase-to-stock feature branch.
- PR #15 CI passed on Python 3.11 and 3.12 at commit de9f3e314995e6397073b9d8d1f24459f7971a67.
- PR #15 remains Draft and depends on PRs #14, #13 and #11. No production release is claimed.

## Milestones and acceptance gates

### 0. Engineering baseline and release discipline
- [x] CI covers Python 3.11 and 3.12, Ruff, pytest, dependency audit, Compose validation, shell/systemd syntax and container build.
- [x] Feature-branch pull requests receive CI checks.
- [ ] Add migration upgrade/downgrade checks against both PostgreSQL and SQLite for every new schema revision.
- [ ] Add branch protection / required status checks and a documented rollback procedure.
- [ ] Publish a single dependency-ordered PR merge plan.

### 1. Identity, tenancy and entitlements
- [x] Tenant-scoped foundation and role/permission primitives.
- [x] Edition/module catalog and persisted tenant module entitlements in feature branches.
- [ ] Complete tenant/branch authorization tests for every write and read endpoint.
- [ ] Add subscription lifecycle, grace period, renewal, suspension and entitlement-change audit.
- [ ] Add administrative recovery and secure account lifecycle workflows.

### 2. Catalog and pricing
- [x] Product foundation.
- [ ] Product variants, barcode/QR aliases, units and conversion rules.
- [ ] Price lists, scheduled pricing, promotion stacking rules and price history.
- [ ] Tax categories, inclusive/exclusive tax calculation and jurisdiction-specific configuration.
- [ ] Import/export validation and duplicate detection.

### 3. Procurement and inventory
- [x] Supplier records and purchase orders.
- [x] Draft → approval → partial receipt → full receipt lifecycle.
- [x] Receipt idempotency, tenant-scoped constraints, immutable inventory movements, audit and outbox.
- [x] Partial-receipt and replay tests; CI passed on both supported Python versions.
- [ ] Supplier invoice capture and three-way matching: purchase order ↔ goods receipt ↔ supplier invoice.
- [ ] Purchase returns, debit notes, landed-cost allocation and supplier credit balances.
- [ ] Lot/batch, serial number, expiry date and recall traceability.
- [ ] Stock counts, cycle counting, adjustment approval and warehouse transfers.
- [ ] Valuation policies: weighted average and FIFO, with immutable revaluation adjustments.
- [ ] Reorder suggestions with supplier lead-time history, MOQ and human approval.

### 4. POS and sales-to-cash
- [ ] Sales orders, quotes, invoices and POS checkout.
- [ ] Barcode/QR scanning, holds, split tender and cashier shift lifecycle.
- [ ] Cash, card-terminal, online and mixed payments through provider adapters.
- [ ] Returns, exchanges, refunds, voids and discount approval controls.
- [ ] Receipt printing, offline queueing and idempotent payment callbacks.
- [ ] Cash drawer opening/closing, over/short reconciliation and supervisor sign-off.

### 5. Finance and accounting
- [ ] Accounts receivable/payable subledgers.
- [ ] Automatic balanced journal entries for purchases, receipts, sales, returns, payments and COGS.
- [ ] Bank/cash reconciliation, settlement matching and payment fee handling.
- [ ] Multi-currency, exchange-rate source and realized/unrealized FX rules.
- [ ] Tax reports, trial balance, general ledger, P&L, balance sheet and cash-flow reports.
- [ ] Period close, locked periods, reversal entries and audit-ready exports.

### 6. Customer, loyalty and CRM
- [ ] Customer profiles, consent and data-retention controls.
- [ ] Points ledger, tiers, rewards, vouchers, coupons and referral campaigns.
- [ ] Earn/burn reversals for refunds and anti-abuse limits.
- [ ] Customer app/PWA, order history, digital receipts and support requests.

### 7. Staff and branch operations
- [ ] Employee roles, branch assignments and least-privilege permission templates.
- [ ] Shift scheduling, attendance, tasks, commissions and payroll export.
- [ ] Approval matrix by amount, role, branch and separation-of-duties policy.
- [ ] Branch-level operational dashboards and consolidated head-office views.

### 8. Reporting and decision intelligence
- [ ] Sales, margin, stock aging, shrinkage, supplier performance and cash dashboards.
- [ ] Product/branch profitability with traceable calculation definitions.
- [ ] Forecasting for demand, replenishment and cash flow with confidence intervals.
- [ ] Explainable anomaly alerts for unusual discounts, refunds, stock adjustments and cash variances.
- [ ] AI remains advisory; price changes, payments, journal postings and other sensitive actions require authorized human approval.

### 9. Offline mode, integrations and resilience
- [ ] Durable local outbox/inbox with retry, deduplication and conflict resolution.
- [ ] Documented SQLite single-node limits; no shared SQLite file on a network filesystem.
- [ ] Provider adapters for payment terminals, accounting exports, messaging and ERP integrations.
- [ ] Backup encryption, scheduled backups, restore drills and recovery objectives.
- [ ] Monitoring, structured logs, health/readiness probes and alerting without leaking secrets.

### 10. Security, acceptance and release
- [ ] Threat model and security review for authentication, tenant isolation, payments and offline sync.
- [ ] End-to-end tests: purchase → receipt → inventory → sale → payment → accounting → reporting.
- [ ] Concurrency tests for idempotency, stock contention and payment callbacks.
- [ ] Accessibility, RTL, Persian/English/Arabic/Turkish localization and responsive-device acceptance.
- [ ] Performance/load tests using realistic multi-branch datasets.
- [ ] Migration rehearsal, rollback rehearsal, release notes, version tags and signed artifacts.
- [ ] Production deployment only after explicit acceptance and backup/restore verification.

## New recommended controls

1. **Three-way invoice matching:** block or route exceptions when invoice quantity/cost differs from the approved order and received quantity.
2. **Approval matrix and segregation of duties:** configurable thresholds; optionally prevent the requester from approving their own high-value order.
3. **Inventory traceability:** lot, serial, expiry and recall workflow, not only aggregate on-hand quantity.
4. **Costing and margin integrity:** define FIFO/weighted-average rules and reconcile stock valuation with the general ledger.
5. **Cashier close and variance review:** require shift close, cash count, terminal settlement and supervisor review.
6. **AI anomaly detection:** flag unusual refund rates, discounts, supplier price jumps, negative-margin sales and stock adjustments; never auto-execute financial actions.
7. **Operational recovery:** test backup restoration, outbox replay and offline conflict recovery, not just backup file creation.
8. **Tenant data export and deletion workflow:** provide governed export, retention and deletion with legal/audit safeguards.

## Definition of 100% for a release

A release milestone is 100% only when all in-scope acceptance items are checked, migrations are verified on supported databases, CI is green, security and end-to-end tests pass, documentation is current, and the corresponding PR stack is merged in dependency order. Production deployment is a separate gated action.
