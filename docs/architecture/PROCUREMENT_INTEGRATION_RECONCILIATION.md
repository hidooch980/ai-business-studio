# Procurement Integration Reconciliation

Status: investigation complete; implementation not yet ported.

## Decision

The purchase-to-pay feature pull requests must not be merged directly into the current `main` lineage. The current `main` tree is a newer/different application foundation:

- Python package discovery is rooted at `src/` and the runtime package is `retail_app`.
- The current package contains security authorization and reporting primitives, but no procurement, inventory, finance-ledger, FastAPI application, or SQLAlchemy model layer.
- The current identity schema is authored as raw PostgreSQL SQL in `migrations/0001_identity_security.sql`.
- The dependent procurement pull requests use a separate `backend.app.*` package, FastAPI + SQLAlchemy + Alembic, and Alembic revisions `0014` through `0019`.

These are architectural differences, not a simple path rename. Copying the feature branch's `backend/` tree and Alembic migrations into `main` would create a second application runtime and a second migration system without proving that either is wired to the current tenant/security foundation.

## Integration target

All new work is staged on `integration/procurement-foundation-2026-11`, created from the current `main` commit. The target remains the current `src/retail_app` package and the existing SQL migration convention unless a reviewed architecture decision explicitly replaces them.

## Dependency order

1. Stabilize the current identity/tenant/branch authorization contract and database migration runner.
2. Establish shared persistence, transaction, audit, idempotency, and outbox primitives that match the current package.
3. Add supplier and purchase-order domain models and APIs.
4. Add goods receipt with append-only inventory movements, stock balance invariants, and concurrent over-receipt protection.
5. Add supplier invoice matching against approved purchase orders and actually received quantities.
6. Add payable ledger posting and manual supplier payment recording with idempotency.
7. Add accounting settings and journal integration only after the existing finance ledger contract is available.
8. Add Moadian connection profiles as configuration-only, with opaque secret references; no live submission.
9. Run the complete integrated migration, tenant-isolation, authorization, rollback, idempotency, concurrency, and end-to-end test suite.

## Porting rules

- Port domain behavior and tests selectively; do not copy the legacy `backend/app` package wholesale.
- Reuse the current tenant and branch authorization boundary; every query and mutation must be tenant-scoped.
- Keep money in integer minor units with explicit currency codes.
- Keep inventory movements and posted journals append-only; corrections use compensating entries.
- Bind idempotency keys to canonical request hashes and test concurrent replay.
- Use atomic transactions for domain state, ledger entries, audit records, and outbox events.
- Do not merge both competing `0017` migrations from the old branch chain. The existing purchase-to-pay branch already has an invoice/payment migration at that revision.
- Do not post tax, freight, or discounts into inventory/GRNI until explicit allocation and accounting rules exist.
- Do not execute real bank transfers or enable live Moadian submissions in this phase.

## Scope gate

Sales, cash register, and POS remain out of scope. They may begin only after the complete purchase and payment dependency chain is integrated and all final tests pass on the integrated candidate.

## Verification status

The upstream feature branches have passing CI reports at their recorded commits, but those results do not validate compatibility with the current `main` tree. No procurement code has yet been ported to this integration branch, no migration has been applied, and no integrated test result is claimed.
