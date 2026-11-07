# Inventory ledger foundation

## Scope

The inventory module is a tenant-scoped stock ledger foundation. It currently supports warehouses and integer-quantity receipt, issue, and adjustment movements.

## API

- `POST /api/v1/inventory/warehouses` — create a tenant warehouse.
- `GET /api/v1/inventory/warehouses` — list active or all tenant warehouses.
- `POST /api/v1/inventory/movements` — record a receipt, issue, or adjustment. Requires `Idempotency-Key`.
- `GET /api/v1/inventory/movements` — list tenant movements.
- `GET /api/v1/inventory/balances` — read current tenant stock projections.

All endpoints require an authenticated session and an authorized tenant selected with `X-Tenant-ID`. Writes also require the session-bound CSRF token. The API never accepts a tenant identifier in the request body.

## Invariants

- A movement's product and warehouse must belong to the same tenant as the movement; composite foreign keys enforce this in the database.
- Receipts add stock, issues subtract stock, and adjustments apply a signed delta.
- Stock cannot become negative. The balance table has a non-negative check constraint, and a database trigger applies each inserted movement to its balance in the same transaction.
- Movement idempotency keys are unique per tenant. Replaying the same key and payload returns the original movement; reusing the key for a different payload is rejected.
- Movement rows are append-only. SQLite and PostgreSQL triggers reject update/delete; PostgreSQL also rejects TRUNCATE.
- The movement ledger is authoritative. Balance rows are projections maintained by database triggers, not manually editable through the API.

## Deliberate limitations

- Quantities are integers in the product's configured unit; fractional quantities and unit conversion are not yet supported.
- Batch/lot numbers, expiry, serial tracking, stock valuation, transfers, reservations, cycle counts, purchase receipts and sales fulfillment are not implemented.
- No warehouse deletion or movement correction is supported. Corrections must be represented by a new compensating adjustment movement.
- Concurrent PostgreSQL stock movements rely on row-level locking and database constraints; load/stress tests are still required before production.

## Verification

CI exercises the migration on SQLite and PostgreSQL, tenant isolation, movement idempotency, non-negative stock, and append-only database triggers. A green CI run does not replace production load testing, accounting reconciliation, or independent security review.
