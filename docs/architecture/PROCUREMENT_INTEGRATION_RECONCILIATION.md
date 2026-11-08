# Procurement Integration Reconciliation

Status: procurement-to-payment implementation is staged on a feature branch; latest Push and Pull Request CI both pass, Ruff passes, and PostgreSQL 16 integration suite reports 54 passed. PR #20 and PR #21 remain drafts; nothing has been merged or deployed.

## Scope gate

The authorized sequence is supplier -> purchase order -> approval -> goods receipt -> three-way invoice match -> accounts payable -> supplier payment -> final integrated verification.

Sales, cash register and POS remain explicitly out of scope until the entire purchase-to-payment chain passes the final integrated test suite. Do not start those modules early.

## Architecture decisions

- Continue in the existing `src/retail_app` package and ordered PostgreSQL SQL migration system.
- Do not copy the legacy `backend.app`/Alembic tree wholesale; it is a different runtime and migration lineage.
- Every business query and write is tenant-scoped; branch operations are checked against trusted AccessContext memberships.
- The HTTP router receives AccessContext from a host-provided authenticated dependency. Tenant, role and branch claims are never accepted from request bodies.
- Financial amounts use integer minor currency units and explicit ISO currency codes.
- State changes, audit records, domain events, outbox records and idempotency completion share one transaction.
- Domain events, audit records, payment allocations and financial ledger entries are append-only. Corrections require compensating records.
- Idempotency keys are bound to canonical request hashes; same-key/same-payload calls replay the original response and same-key/different-payload calls conflict.

## Current staged implementation

### Database migrations

- `0002_transactional_infrastructure.sql`: tenant-scoped idempotency, domain events, outbox and audit.
- `0003_suppliers_purchase_orders.sql`: suppliers, purchase orders and lines.
- `0004_receipts_invoices_payments.sql`: goods receipts and discrepancy lines, supplier invoices and invoice lines, accounts payable, supplier payments, payment allocations and double-entry ledger lines.
- All new tenant tables enable and force RLS with transaction-local tenant context.
- Invoice lines have a composite foreign key to the exact PO line and receipt line to prevent cross-order/line matching.

### HTTP endpoints

The router factory is `retail_app.api.procurement.create_procurement_router(database, context_dependency)`. The host application must supply its trusted authenticated-context dependency.

- `POST /api/procurement/suppliers`
- `POST /api/procurement/purchase-orders`
- `GET /api/procurement/purchase-orders`
- `GET /api/procurement/purchase-orders/{order_id}`
- `PATCH /api/procurement/purchase-orders/{order_id}` (draft only)
- `POST /api/procurement/purchase-orders/{order_id}/approve` (owner/admin only)
- `POST /api/procurement/purchase-orders/{order_id}/receipts`
- `POST /api/procurement/supplier-invoices/match`
- `GET /api/procurement/inventory/stock?branch_id=...&item_id=...` (derived from immutable movements)
- `GET /api/procurement/accounts-payable`
- `POST /api/procurement/supplier-payments`

All write endpoints require `Idempotency-Key`. The host must mount this router into its FastAPI application and provide authentication; this branch does not claim an already-running production API.

### Receipt and discrepancy controls

- Only approved or partially received orders can receive goods.
- Received quantity must equal accepted plus rejected quantity.
- Rejections and overdelivery require a discrepancy code.
- Cumulative delivered quantity above ordered quantity is rejected unless an explicit overdelivery flag is set by a tenant owner/admin; branch managers cannot authorize overdelivery.
- Accepted quantities create immutable, tenant/branch-scoped inventory movements in the same transaction as the receipt; rejected quantities never enter stock.
- On-hand quantity is derived by summing the movement ledger and is exposed through the branch-scoped stock API.
- Receipt value posts Inventory debit / GRNI credit based on accepted quantities and PO unit prices.
- The movement ledger is not yet linked to a catalog/item-master FK, warehouse/bin locations, stock reservations, costing layers or downstream issue/adjustment workflows. Do not treat those broader warehouse functions as complete.

### Three-way invoice match

- Invoice supplier and currency must match the PO.
- Each invoice line must point to a receipt line belonging to the same PO and PO line.
- Invoice quantity is checked against accepted received quantity; invoice unit price is checked against PO price.
- Header total must equal the exact sum of invoice line totals.
- Any mismatch leaves the invoice in `disputed` status and does not create an AP balance.
- Only a matched invoice creates one AP item and posts GRNI debit / Accounts Payable credit.
- Tax, freight, discounts, exchange differences and rounding allocation are not yet supported; they must be explicitly designed before production use.

### Accounts payable and payment

- AP records retain original amount, outstanding amount, currency, due date and open/partial/paid status.
- Supplier payments are recorded with a unique tenant-scoped reference and explicit allocation to one or more AP items.
- Allocation total must equal payment amount and cannot exceed any AP outstanding balance.
- Payment posts Accounts Payable debit / Bank, Cash or clearing credit; ledger entries are immutable.
- Payment is a manual accounting record only. No bank transfer, payment gateway or external financial execution is performed.
- The ledger writer emits balanced debit/credit pairs, and a deferred PostgreSQL constraint trigger rejects an unbalanced journal at commit. A full chart-of-accounts, period close and reversal workflow remain future finance work.

## Authorization

- Tenant owner/admin: supplier directory writes, PO approval, invoice matching, AP visibility and supplier payment recording.
- Branch manager: read/create/edit draft purchase orders and post goods receipts only inside assigned branches.
- Employee/customer roles do not gain procurement write privileges.
- Every API context must originate from trusted authentication and membership resolution, never request data.

## Verification plan

1. Ruff and unit tests.
2. Fresh PostgreSQL migration application and RLS checks.
3. Supplier and PO create/read/edit/approve with audit/event/idempotency.
4. Receipt accepted/rejected/short/overdelivery and concurrent receipt checks.
5. Three-way invoice exact match, price/quantity/total mismatch and disputed/no-AP behavior.
6. AP due date, partial/full payment, allocation bounds and duplicate payment replay.
7. Balanced ledger totals by source and immutable audit/event/payment/ledger checks.
8. End-to-end lifecycle from supplier creation through fully settled payable.
9. Re-run the complete suite on the final integrated candidate before merge review.

Latest verified feature head: `c6b5a71735699e16aeeaae13b91900c27bd0b71f`. Push and Pull Request CI both passed; Ruff passed; PostgreSQL 16 integration and full test suite: 54 passed. The router factory still needs to be mounted by the host application with its authenticated AccessContext dependency. No production database migration, bank execution, Moadian submission, deployment or merge to main has occurred.
