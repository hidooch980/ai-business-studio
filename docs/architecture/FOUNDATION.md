# Foundation Architecture

## Initial boundary

The first increment contains only the HTTP application shell, environment-backed non-secret settings, and a health endpoint. It deliberately does not connect to a production database, payment provider, bank, or AI service.

## Planned domain modules

- Identity and tenancy
- Catalog and pricing
- Sales and POS
- Inventory and warehouse
- Procurement and suppliers
- CRM and customer support
- Finance and accounting
- Payments and reconciliation
- Reporting and semantic metrics
- AI intelligence and management copilot

Each module will own its application services, domain rules, persistence interfaces, API contracts, and tests. Shared kernel code must remain small and stable.

## Persistence strategy

PostgreSQL is the central multi-user database. SQLite is reserved for a single local application node. Multiple tills must communicate with a local application service over LAN; they must not open a shared SQLite file over a network filesystem.

Offline synchronization will use durable outbox/inbox records, globally unique event identifiers, idempotent consumers, retry with backoff, and explicit conflict handling. Financial and inventory mutations must be atomic with their outbox records.

## Financial correctness

Money is represented with decimal arithmetic and an explicit currency. Sales, refunds, fees, settlements, and ledger postings remain distinct concepts. A successful payment authorization is not automatically a bank settlement. Corrections use compensating entries rather than destructive edits.

## AI boundaries

AI components consume governed metrics and traceable source data. Forecasts must be labeled as forecasts and include assumptions and uncertainty. AI recommendations are advisory; sensitive financial or administrative actions require authorization and audit logging.
