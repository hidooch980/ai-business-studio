# Smart POS (Cashier) — Product and Technical Scope

## Goal

Deliver a fast, tenant-isolated point-of-sale workflow for cashiers, with a Persian-first RTL experience and a stable API contract that can later support desktop terminals, tablets, barcode scanners, receipt printers, cash drawers, and payment terminals.

This document records approved scope. A capability is not considered implemented until its schema, API/UI, authorization, audit trail, automated tests, and operational evidence are merged on the same verified commit.

## Cashier workspace

- Product lookup by barcode, QR payload, SKU, name, and recent/favorite items.
- Category filters, fast quantity editing, line removal, and keyboard/scanner-friendly operation.
- Customer selection or quick customer creation subject to permissions.
- Live subtotal, line/whole-ticket discounts, tax breakdown, payable total, and clear rounding rules.
- Price/discount overrides protected by granular permissions and audit events.
- Stock availability checks at checkout, with reservation/fulfillment rules preventing overselling.
- Suspend/resume a sale, quote/hold workflow, and controlled voiding.
- Accessible responsive layout with RTL Persian and LTR English support.

## Payments

Support one or multiple tender lines on one sale:

1. Cash: amount tendered, change due, cashier and drawer attribution.
2. Card terminal: terminal selection, amount, provider/terminal reference, approval/decline/timeout state, and reconciliation reference. Do not store PAN, CVV, PIN, or track data.
3. Online payment: hosted checkout/payment link or QR, signed provider webhook verification, expiry, asynchronous confirmation, and replay protection.
4. Split tender: any permitted combination of cash, card, and online payments; enforce that successful captured amounts do not exceed the amount due, and that the sale is not settled until the required amount is confirmed.

Payment states must be explicit (created, pending, authorized, captured/settled, failed, cancelled, refunded, partially_refunded, unknown/reconciliation_required). A timeout is not proof of failure: query/reconcile provider state before retrying. Use tenant-scoped idempotency keys and provider idempotency where supported. Never mark an order paid based only on a client redirect or cashier assertion.

## Receipts, invoices, and returns

- Printable receipt and legally compliant invoice adapter once jurisdictional requirements are configured.
- Digital receipt delivery by SMS/email only after consent and provider configuration.
- Reprint history and duplicate-copy marking.
- Full and partial returns tied to original sale lines and original payment allocations.
- Refunds use compensating records; never edit or delete captured payment or posted accounting history.
- Return permissions, reason codes, returned-stock inspection/disposition, and refund reconciliation.

## Cash drawer and shifts

- Open shift with opening float and assigned cashier/register.
- Cash in/out movements with reason, approval policy, and audit event.
- Shift handover with dual acknowledgement where configured.
- Close shift with expected cash, counted cash, variance, card/online totals, and reconciliation report.
- Prevent closing with unresolved pending payments or require an explicit authorized exception.
- Never expose another cashier's shift data without permission.

## Inventory, catalog, and customer integration

- Decrement stock only through the authoritative inventory ledger in the same business transaction as sale fulfillment.
- Support barcode/QR workflows, categories, units/conversions, bundles, and product variants in staged delivery.
- Stock reservation, release on cancellation/expiry, and race-safe availability checks.
- Customer accounts, store credit/credit sales only under explicit credit limits and approval.
- Loyalty points and promotions only after deterministic pricing and refund rules exist.

## Offline operation

- Offline mode may queue draft sales and non-financial actions with a device-generated operation ID.
- Do not claim card/online payment success offline. Cash offline sales must be visibly marked provisional until server synchronization.
- Server remains authoritative for stock, price, tax, customer credit, and final sale numbering.
- On reconnect, replay idempotently, detect conflicts, and provide a cashier/supervisor resolution queue; never silently overwrite or duplicate a sale.
- Device identity, local data encryption, expiry, and remote session/device revocation are required before production offline use.

## Analytics and AI assistance

- Sales by cashier/register/product/category/payment type, shift variance, returns, discounts, and margin where cost data is reliable.
- Forecast demand and suggest replenishment/discounts with explainable inputs and confidence.
- AI suggestions are advisory only; pricing, refunds, stock adjustments, and financial postings require deterministic policy and human authorization.
- Tenant-scoped analytics, consent controls, retention policy, and no cross-tenant training/data leakage.

## Security, accounting, and reliability invariants

- Tenant scope enforced in every query and by composite foreign keys where relationships cross tenant-owned tables.
- Permission checks for price overrides, refunds, voids, cash movements, shift close/reopen, customer credit, and reports.
- Append-only audit trail for sale/payment/refund/shift state transitions.
- Integer minor units for money; explicit currency and tax/rounding policy; no floating-point financial arithmetic.
- Sales, inventory movements, accounting journals, and outbox events commit atomically where they share the database.
- External provider calls occur outside long-running database transactions; use durable payment intents/outbox, signed webhooks, replay defense, and reconciliation jobs.
- Idempotency at API, database, worker, and provider boundaries; unique constraints are the final duplicate defense.
- Secrets remain server-side; no raw cardholder data is stored.
- Monitoring for payment pending age, webhook failures, outbox lag, reconciliation mismatches, drawer variances, and offline queue age.

## Delivery sequence

1. Domain model and API contracts: registers, shifts, sales, sale lines, payment intents/allocations, state machine, audit events, and idempotency.
2. Cash-only checkout and receipt with atomic inventory fulfillment and journal posting.
3. Cash drawer open/close, shift reconciliation, voids, and role controls.
4. Card terminal adapter interface plus sandbox/mock contract tests; then a selected real provider integration.
5. Hosted online payment adapter, signed webhooks, refund flow, and reconciliation.
6. Split tender and partial/full returns with exact payment allocation.
7. Barcode/QR hardware workflows, customer display, printer/cash-drawer device adapters.
8. Offline draft queue, synchronization and conflict resolution.
9. Reports, loyalty/CRM, AI recommendations, load/security testing and staged rollout.

## Release gates

No live payment provider, cash drawer, or offline mode is production-enabled until provider/device contract tests, concurrency and replay tests, reconciliation, monitoring/alerts, recovery procedures, security review, and staging acceptance are complete. CI success alone does not authorize live money movement.
