# Purchase-to-Pay Workflow

## Goal

Extend the verified purchase-to-stock workflow into a controlled supplier invoice, accounts-payable and payment lifecycle. The workflow must not change stock quantities when an invoice is recorded; stock is changed only by an approved goods receipt.

## Target lifecycle

1. Draft supplier invoice is created against an approved purchase order.
2. Invoice lines are matched to purchase-order lines and accepted goods receipts.
3. Quantity, unit-cost, currency, tax and total differences are reported as explicit exceptions.
4. An authorized approver approves the matched invoice or resolves a documented exception.
5. Posting creates a balanced, idempotent journal entry and an accounts-payable balance in the same database transaction.
6. Partial or full supplier payments reduce the payable balance and create balanced payment journal entries.
7. Reversals use compensating journal entries; posted invoices and payments are never edited or deleted.

## Three-way matching

- Purchase order: ordered quantity and agreed unit cost.
- Goods receipt: accepted quantity actually received into the warehouse.
- Supplier invoice: billed quantity and unit cost.
- Invoice quantity cannot exceed received quantity less previously invoiced quantity.
- Unit-cost variances, tax differences, duplicate invoice numbers and currency mismatches are recorded as exceptions; they must not silently post.
- A tenant-configurable tolerance policy may allow low-value variances with an audit trail and appropriate approval.

## Accounting contract

- Invoice posting: debit inventory/expense and recoverable input tax as applicable; credit accounts payable.
- Payment posting: debit accounts payable; credit the selected cash/bank account.
- All entries use the existing tenant-scoped double-entry journal, integer minor units, an open accounting period, and idempotency keys.
- Invoice/payment state, journal entries, audit events and outbox events must commit atomically.
- The tenant must configure valid active financial accounts before posting; no implicit hard-coded chart-of-account assumptions.

## Security and controls

- Tenant isolation and procurement/finance module entitlements are checked on every operation.
- CSRF protection applies to browser write requests.
- Separate permissions are required for invoice creation, approval, posting and payment execution.
- Approval policy supports amount thresholds, branch scope and optional separation of duties.
- Duplicate supplier invoice numbers and repeated payment requests are rejected or idempotently replayed.
- Posted documents are immutable; corrections use credit notes, payment reversals or journal reversals.

## Acceptance tests

- Full, partial and multiple receipts followed by matching invoices.
- Reject invoiced quantity above received quantity and above remaining uninvoiced quantity.
- Detect unit-cost, currency, tax and total mismatches.
- Reject duplicate supplier invoice numbers within a tenant.
- Prove one tenant cannot access another tenant's supplier, order, invoice, payment or journal.
- Verify invoice posting creates one balanced journal and no stock movement.
- Verify partial/full payments update AP balances and create balanced journals.
- Verify idempotent replay and conflicting idempotency-key payloads.
- Verify rollback leaves no orphan invoice, journal, payment or outbox record.
- Run migrations and end-to-end tests on PostgreSQL 16 and SQLite.

## Explicit exclusions for this stage

- Automatic bank transfers and custody of payment credentials.
- Tax filing or submission to government systems.
- Automatic acceptance of invoice variances by AI.
- Unreviewed posting to production accounting periods.

AI may rank discrepancies and recommend actions, but invoice approval and payment execution remain authorized human actions.