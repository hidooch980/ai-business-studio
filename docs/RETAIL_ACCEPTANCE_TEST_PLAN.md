# Retail Platform — Acceptance and Verification Plan

Status: acceptance criteria approved; tests have not yet been executed against an implementation.

## A. POS and payments
- Cash sale; card terminal reference capture; online provider callback; split tender; customer credit where enabled.
- Reject underpayment and overpayment unless an explicit change-due policy applies.
- Idempotent payment callbacks and request retries; no duplicate payment or sale.
- Void, return and exchange with authorization, reason, original-sale linkage and compensating entries.
- Shift opening/closing, cash count, variance report and audit record.

## B. Catalog and inventory
- SKU/barcode uniqueness within the configured scope.
- Variant, unit conversion and tax configuration validation.
- Goods receipt, sale issue, return, adjustment, transfer and cycle count.
- Stock ledger reconciliation against on-hand balance.
- Concurrent sale/reservation tests; no silent negative stock unless policy explicitly allows it.
- Optional serial, batch and expiry tracking tested only when enabled.

## C. Finance
- Every posted sale, payment, return, purchase and expense maps to balanced journal entries.
- Reversal/adjustment instead of destructive edits.
- Cash/bank/card settlement reconciliation and duplicate statement import handling.
- Profit/margin reports account for cost method, discounts, returns and expenses.
- Period close and permission enforcement.

## D. Multi-branch and tenant isolation
- One-branch deployment works without multi-branch UI clutter.
- Multi-branch stock, registers, users, pricing and reporting are correctly scoped.
- Cross-tenant and unauthorized cross-branch API access is denied.
- Inter-branch transfer has paired dispatch/receipt states and auditable discrepancies.

## E. Offline and synchronization
- POS remains usable during network loss for supported operations.
- Local queue survives process restart and device restart.
- Reconnection delivers each event exactly once in effect (idempotent processing).
- Out-of-order, duplicated and delayed events are handled safely.
- Conflicts are visible and resolvable; no silent loss or overwrite.
- Backup and restore preserve local pending events and central records.

## F. Security and audit
- Authentication, password/session policy, RBAC and least privilege.
- Server-side tenant/branch checks on every protected operation.
- CSRF protection where cookie-authenticated writes are used; secure cookie settings.
- Secrets and payment card data are absent from logs, source and database.
- Audit trail for refunds, voids, overrides, price changes, stock adjustments and financial postings.

## G. AI, reporting and localization
- AI forecasts expose data window, confidence/uncertainty and explanation.
- AI outputs are advisory; no sensitive action is auto-executed.
- Reports reconcile to source ledgers and support scoped export.
- Persian/Arabic RTL, English/Turkish LTR, locale-aware dates, numbers and currencies.
- Accessibility and responsive desktop/mobile layouts.

## Release gate
A release is accepted only when:
1. Unit, integration, API, migration and end-to-end suites pass.
2. Critical security and tenant-isolation tests pass.
3. Payment, stock and journal invariants pass under retry/concurrency tests.
4. Offline recovery and backup-restore tests pass.
5. No unresolved critical/high severity defects remain.
6. Build artifacts and deployment instructions are reproducible.

Do not label a build stable, signed, published or production-ready until corresponding evidence exists.
