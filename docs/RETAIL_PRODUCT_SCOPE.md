# AI Smart Retail — Approved Product Scope

Status: approved specification; implementation and runtime verification are not yet complete.

## Product definition
A general-purpose retail management platform for one store or multiple branches. The same core serves grocery, apparel, electronics, home goods, mobile, parts and other retail categories. Trade-specific workflows are optional extensions.

## User-facing applications
1. **Owner/admin web console** — tenant/store/branch setup, finance, purchasing, inventory, staff, permissions, loyalty configuration, reports, AI command center, audit and recovery.
2. **Manager app** — branch KPIs, approvals, cash/shift oversight, stock exceptions, purchasing requests, staff schedules/tasks, customer and loyalty insights. Managers see only assigned branches and permitted data.
3. **Employee app** — role-specific POS, barcode lookup, customer lookup, assigned tasks, shift start/end, stock count/receive/transfer workflows, sales attribution and announcements. Refunds, overrides and adjustments require permission and reason.
4. **Customer app / PWA** — digital membership card, points and tier progress, rewards, coupons, offers, order history, receipts, saved products, wishlist, store locator, support and privacy/consent controls. Online ordering is enabled only when commerce and fulfillment are configured.
5. **Shared backend/API** — one source of truth, shared identity, tenant/branch authorization, event bus/outbox and audit trail. Applications are separate clients, not separate databases.

## Core business modules
1. **Store and tenant setup** — tenant isolation, store profile, branches, registers, timezone, currency, tax and receipt settings, fiscal periods.
2. **Identity and access** — users, roles, branch/register scopes, least-privilege permissions, session controls, MFA-ready design and audit.
3. **Catalog** — products, categories, variants, SKU, barcode/QR, units, tax class, cost/price history, optional serial/batch/expiry/attributes.
4. **POS and sales** — scan/search, cart, customer association, authorized discounts, quotes/receipts/invoices, suspend/resume, void with reason, returns/exchanges, cash/card/online/split/account payments.
5. **Payments** — cash, card terminal, online gateway, split tender, refunds, provider callbacks, settlement matching and idempotency. Store references/tokens only; never store raw card data.
6. **Cash management** — register float, cash in/out with reason, shift handover, expected-vs-counted reconciliation and cashier close.
7. **Inventory** — append-only stock ledger, receipts, issues, adjustments, transfers, reservations, cycle counts, reorder thresholds, warehouses and branch stock.
8. **Purchasing** — suppliers, purchase orders, receiving, supplier invoices, returns and payables.
9. **Retail finance** — append-only journals, expenses, receivables/payables, cash/bank, settlement matching, trial balance and period close. Corrections use reversal/adjustment entries.
10. **Customers and CRM** — profiles, purchase history, balances, support, consent/preferences, segments and communication history.
11. **Loyalty engine** — configurable earn/burn rules, tiers, points ledger, rewards, coupons, campaigns, referrals, expiry, returns reversal, fraud controls and campaign analytics.
12. **Staff operations** — employee profiles, shifts, tasks, announcements, sales attribution, simple commissions, attendance and payroll export; advanced HR/payroll optional.
13. **Reporting/BI** — sales, margin, stock valuation, shrinkage, returns, cash variance, balances, branch comparison and CSV/XLSX/PDF exports.
14. **Multi-branch** — branch-scoped inventory/registers/prices/users, inter-branch transfers and consolidated reporting.
15. **Offline operation** — durable local queue, idempotent sync, retry/backoff, conflict detection, sync status and recovery.
16. **AI advisory** — demand forecast, reorder suggestions, margin anomaly detection, financial guard, branch insights and explainable recommendations.
17. **Resilience/security** — backup/restore verification, monitoring, audit, access review, retention and incident recovery.

## Loyalty rules and financial integrity
- Points are a separate append-only liability/reward ledger, not cash and not an editable customer balance.
- Every earn, redeem, expire, adjustment and reversal has a unique event, source transaction, actor/rule version and timestamp.
- Sale returns reverse the points earned on the returned portion; redeemed rewards are restored only according to explicit policy.
- Define eligible subtotal, tax/shipping exclusions, rounding, caps, minimum spend, expiry, tier evaluation and refund treatment in versioned rules.
- Prevent duplicate accrual/redemption with idempotency keys and atomic balance/availability checks.
- Coupon stacking, branch applicability, customer eligibility, budget and campaign windows are explicit.
- No negative point balance unless a documented debt policy is explicitly enabled.
- Loyalty credit and cash-equivalent rewards require accounting/tax treatment review for each jurisdiction.

## Optional capabilities
Online storefront/marketplace, delivery/fulfillment, advanced CRM automation, advanced payroll/attendance, industry-specific fields, serial/batch/expiry tracking, external accounting integrations and advanced procurement automation.

## Architecture
- Python + FastAPI modular monolith; REST API under /api/v1.
- PostgreSQL central database; SQLite WAL on a single local node for offline mode (never share SQLite over network filesystem).
- Tenant and branch authorization enforced server-side on every operation.
- Transactional outbox/inbox, event IDs, idempotency, retry/backoff and explicit conflict resolution.
- Financial, inventory and loyalty ledgers are append-only; corrections use compensating entries.
- Persian/English/Arabic/Turkish; RTL for Persian and Arabic; localized dates, numbers and currency.
- Responsive web/PWA first; native mobile wrappers can follow without changing domain contracts.

## Non-negotiable invariants
1. A sale cannot be marked paid unless payment records reconcile to amount due.
2. Retries cannot duplicate sales, payments, stock movements, journals, points or redemptions.
3. Returns link to original sales and create compensating entries.
4. Tenant/branch boundaries are enforced server-side.
5. Posted financial, stock and loyalty ledgers are not destructively edited.
6. Offline transactions remain durable until centrally acknowledged.
7. Concurrent stock and point redemptions cannot silently oversell/overdraw.
8. AI is advisory; sensitive actions require authorized human approval.
9. Every override, void, refund, adjustment, reward grant and reconciliation records actor, time and reason.
10. Backups count as valid only after restore verification.

## Delivery order
1. App foundation, config, health, migrations, CI and security.
2. Tenant/store/branch/identity/RBAC.
3. Catalog, POS, payments and cash shifts.
4. Inventory and purchasing.
5. Finance ledger and reconciliation.
6. Customer identity, consent and loyalty ledger/rules.
7. Manager and employee workflows; customer app/PWA.
8. Reporting, multi-branch sync and offline recovery.
9. AI decision engine and advisory modules.
10. Localization, security hardening, end-to-end tests and release packaging.

A capability is complete only when tests pass and runtime behavior is verified. This specification is not evidence of implementation or production readiness.
