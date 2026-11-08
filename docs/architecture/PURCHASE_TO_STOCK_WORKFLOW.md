# Purchase-to-stock workflow contract

Status: **Implemented in feature branch; CI and review pending**

This workflow is delivered as an additive module over the versioned tenant-entitlement foundation.

## Lifecycle

`supplier -> purchase order draft -> authorized approval -> partial/full goods receipt -> immutable inventory movements -> updated on-hand balance`

## API

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/procurement/suppliers` | `procurement.manage` | Create supplier |
| GET | `/api/v1/procurement/suppliers` | `procurement.read` | List tenant suppliers |
| POST | `/api/v1/procurement/purchase-orders` | `procurement.manage` | Create draft purchase order |
| GET | `/api/v1/procurement/purchase-orders` | `procurement.read` | List purchase orders |
| POST | `/api/v1/procurement/purchase-orders/{id}/approve` | `procurement.approve` | Approve a draft |
| POST | `/api/v1/procurement/purchase-orders/{id}/receipts` | `procurement.manage` | Receive one or more lines |

All write endpoints require CSRF protection and tenant-scoped RBAC plus the active procurement module entitlement.

## Controls

- Supplier, product, warehouse, order and order-line lookups are tenant-scoped.
- Orders start in draft and cannot be received until approved.
- Receipts may be partial; the order moves through approved, partially_received and received.
- Over-receiving is rejected.
- Receipt idempotency keys are tenant-scoped and bound to a canonical request hash; replaying the same key and payload does not post stock twice.
- Each accepted receipt line creates an immutable inventory movement, emits an outbox event and is covered by audit events.
- Existing inventory balance database triggers remain the sole mechanism applying movements to on-hand balances.
- Data is not deleted by status transitions.

## Not yet included

- Supplier invoice matching and accounts-payable posting.
- Purchase returns, debit notes, landed-cost allocation and tax documents.
- Automated PO creation from AI suggestions. Smart replenishment remains advisory; a user creates and approves a PO.
- Vendor portal, RFQ/tender management and multi-currency settlement.

## Verification target

The integration test migrates a fresh SQLite database, registers a tenant, upgrades it to Growth, creates supplier/product/warehouse, creates and approves an order, posts partial receipts, verifies replay protection, and confirms the final on-hand quantity and audit trail. CI also exercises the repository's PostgreSQL test service.


## Purchase-to-pay (initial implementation)

The dependent feature branch also introduces supplier invoice and payable settlement primitives:

- Supplier invoice draft creation linked to a tenant-owned supplier and purchase order.
- Invoice line matching against received purchase-order quantities and the approved unit cost.
- Cumulative invoiced quantity checks across matched, approved, posted, partially paid, and paid invoices.
- Explicit invoice approval before posting to the accounts-payable subledger.
- Partial and full manual payment recording with currency checks, outstanding-balance limits, and idempotency keys.
- Tenant-scoped composite foreign keys, audit events, and unique invoice/payment identifiers.

### API

- `POST /api/v1/procurement/payables/invoices`
- `POST /api/v1/procurement/payables/invoices/{invoice_id}/match`
- `POST /api/v1/procurement/payables/invoices/{invoice_id}/approve`
- `POST /api/v1/procurement/payables/invoices/{invoice_id}/post`
- `POST /api/v1/procurement/payables/invoices/{invoice_id}/payments`
- `GET /api/v1/procurement/payables/invoices`

### Deliberate limitations

This is an initial accounts-payable subledger workflow, not a complete bank/payment integration. Posting currently changes the AP subledger state; automatic general-ledger journal generation, tax calculation, invoice attachments/OCR, payment-provider execution, bank reconciliation, multi-currency FX, credit notes, and configurable price/quantity variance tolerances remain future work. No real money is transferred by the manual payment endpoint.

### Verification targets

The integration suite covers a purchase order through receipt, invoice matching, approval, AP posting, partial payment, idempotent replay, and final settlement. It also verifies cross-tenant supplier list isolation and rejection of tenant switching. Concurrent receipt behavior must be exercised against PostgreSQL with parallel transactions before production approval.


## General-ledger integration (purchase accounting)

| Event | Debit | Credit |
|---|---|---|
| Goods receipt | Inventory asset | Goods received not invoiced (GRNI) liability |
| Approved supplier invoice posting | GRNI liability | Accounts payable liability |
| Manual supplier payment record | Accounts payable liability | Cash/bank asset |

The mappings are configured through GET/PUT /api/v1/procurement/accounting-settings. The four account codes must be distinct, active, tenant-owned, and of the expected account type. The configured base currency is authoritative for purchase-order line costs, invoice matching, receipts and payments. Posting uses the existing double-entry ledger, integer minor units, idempotency keys, audit records and open accounting-period checks. Procurement state changes and journal entries are committed in the same database transaction.

The manual payment API records an accounting payment and does not initiate a bank transfer. A bank statement reconciliation or payment-provider integration is not included. Multi-currency/FX, tax, credit notes, landed-cost allocation and configurable variance tolerances remain out of scope for this increment.
