# AI Smart Retail — Approved Product Scope

Status: approved specification; implementation and runtime verification are not yet complete.

## Product definition

A general-purpose retail management platform for one store or multiple branches. The same core product serves grocery, apparel, electronics, home goods, mobile, parts, and other retail categories. Trade-specific fields and workflows are opt-in extensions, not mandatory core screens.

## Core modules

1. **Store and tenant setup** — tenant isolation, store profile, branch, register, timezone, currency, tax settings, receipt settings, fiscal periods.
2. **Identity and access** — users, roles, branch/register scopes, least-privilege permissions, session controls, audit trail.
3. **Catalog** — products, categories, variants, SKU, barcode/QR, units, tax class, cost and price history, optional serial/batch/expiry/attributes.
4. **POS and sales** — fast scan/search, cart, customer association, discounts with permission limits, quotations/receipts/invoices, suspend/resume sale, void with reason, returns/exchanges, cash/card/online/split/tender-on-account payments.
5. **Cash management** — register opening float, cash in/out with reason, shift handover, expected-vs-counted reconciliation, cashier close.
6. **Inventory** — stock ledger, receipts, issues, adjustments, transfers, reservations, cycle counts, reorder thresholds, multi-warehouse and branch stock.
7. **Purchasing** — suppliers, purchase orders, goods receipt, supplier invoices, returns to supplier, payable balance.
8. **Retail finance** — append-only journal/ledger, sales and purchase postings, expenses, receivables/payables, cash/bank accounts, settlement matching, trial balance and period reports. Corrections use reversal/adjustment entries; never silently overwrite posted financial records.
9. **Customers** — basic profiles, purchase history, balances, consent and contact preferences. Advanced CRM/marketing automation remains optional.
10. **Staff operations** — cashier/seller profiles, shifts, sales attribution, simple commission and payroll export. Advanced HR/payroll is optional.
11. **Reporting** — sales, margin, stock valuation, shrinkage, returns, cash variance, supplier/customer balances, branch comparisons, daily/monthly/yearly reports, CSV/XLSX/PDF export.
12. **Multi-branch** — branch-scoped stock/registers/prices/settings, inter-branch transfers, consolidated management reporting, central user administration.
13. **Offline operation** — local durable transaction queue, idempotent sync, retry/backoff, conflict detection, sync status, safe recovery. Never share a SQLite database file over a network filesystem.
14. **AI assistance** — demand/sales forecasts, reorder suggestions, margin anomaly detection, unusual transaction flags, explainable insights. AI output is advisory; posting, payment, price changes and other sensitive actions require authorized human approval.

## Optional capabilities

- Online storefront and marketplace connectors
- Loyalty, campaigns and advanced CRM
- Advanced payroll and attendance hardware
- Industry-specific product attributes and workflows
- Serial number, batch and expiry tracking (enabled by product category)
- Advanced procurement automation and external accounting integrations

## Explicit exclusions from core

Manufacturing/production planning, industrial maintenance, fleet management, project management, enterprise HR suites, and unrelated industrial ERP modules.

## Architectural baseline

- Backend: Python + FastAPI; modular monolith with explicit domain boundaries.
- Central persistence: PostgreSQL.
- Local single-node/offline persistence: SQLite in WAL mode, accessed only by the local application process.
- API: versioned REST under /api/v1; request validation and documented error contracts.
- Sync: transactional outbox/inbox, globally unique event IDs, idempotency keys, per-tenant and per-branch authorization, conflict queue and operator resolution.
- Financial and stock facts: append-only ledgers; corrections are reversal or adjustment events.
- Security: tenant isolation enforced in service/repository boundaries; RBAC; audit log; encrypted transport; secrets outside source control; backups with tested restore.
- Localization: Persian (RTL), English, Arabic (RTL), Turkish; locale-aware numbers, dates, currency and tax labels.

## Non-negotiable invariants

1. A sale cannot be marked paid unless payment records reconcile to the amount due.
2. Retrying a request or sync event cannot create duplicate sales, payments, stock movements or journal postings.
3. A return references the original sale where available and creates compensating stock/financial entries.
4. Branch and tenant boundaries are enforced server-side, not only in the UI.
5. Posted financial and stock ledgers are not destructively edited.
6. Offline transactions remain durable until acknowledged by the central service.
7. Concurrent stock changes cannot silently oversell; reservation/availability policy is explicit.
8. AI recommendations never autonomously execute sensitive financial or inventory actions.
9. Every privileged override, void, refund, stock adjustment and reconciliation has an actor, timestamp and reason.
10. Backups are considered valid only after restore verification.

## Delivery order

1. Repository foundation, configuration, health, migrations, CI and security baseline.
2. Tenant/store/branch/user/access model.
3. Catalog and product variants/barcodes.
4. POS, payments, returns and cash shifts.
5. Inventory ledger and purchasing.
6. Finance ledger and reconciliation.
7. Staff, customers and reporting.
8. Multi-branch synchronization and offline recovery.
9. AI advisory services.
10. Localization, hardening, end-to-end tests and release packaging.

A capability is complete only when its automated tests pass and its operational behavior is verified. This specification alone is not evidence of implementation or production readiness.
