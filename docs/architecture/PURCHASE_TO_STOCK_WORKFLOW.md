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
