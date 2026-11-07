# AI Business Studio

A modular, offline-capable retail management platform for single-store and multi-branch businesses in Iran and international markets.

## Approved product scope

The product is a general-purpose retail system. Grocery, apparel, electronics, home goods, mobile, parts and other retail categories use the same core; industry-specific fields and workflows are optional extensions.

- POS, barcode/QR, sales, returns and split payments
- Catalog, variants, pricing and tax configuration
- Inventory, warehouses, stock ledger and transfers
- Purchasing, suppliers and goods receiving
- Retail finance, cash/bank, receivables/payables and reconciliation
- Customers, staff shifts and basic commissions
- Single-branch and multi-branch management
- Offline-capable operation and durable synchronization
- Reporting and explainable, advisory AI

Manufacturing, industrial maintenance, fleet management, project management and enterprise HR are excluded from the retail core.

See:
- [Approved retail product scope](docs/RETAIL_PRODUCT_SCOPE.md)
- [Acceptance and verification plan](docs/RETAIL_ACCEPTANCE_TEST_PLAN.md)

## Architecture decisions

- **Backend:** Python and FastAPI.
- **Architecture:** modular monolith with explicit domain boundaries and versioned contracts.
- **Central database:** PostgreSQL.
- **Local/offline mode:** SQLite in WAL mode on a single local node, with an application-level synchronization protocol. Never share a SQLite database file over a network filesystem.
- **API:** versioned REST endpoints under `/api/v1`.
- **Financial and inventory records:** append-only ledgers; corrections use reversal or adjustment entries.
- **Multi-tenancy:** tenant- and branch-scoped data access and authorization checks at service boundaries.
- **Synchronization:** transactional outbox/inbox, idempotency keys, retry handling and explicit conflict resolution.
- **AI:** provider-independent interfaces; AI suggestions are advisory and sensitive actions require authorized human approval.
- **Localization:** Persian, English, Arabic and Turkish; RTL for Persian/Arabic.

## Repository status

The approved product scope and acceptance plan are documented. This repository is still at the specification/bootstrap stage; documentation is not evidence that runtime features are implemented or production-ready. Implementation, automated tests, security verification and release checks must be completed before a stable release can be claimed.

## Delivery sequence

1. Application foundation, configuration, health, migrations, CI and security baseline.
2. Tenant/store/branch/user/access model.
3. Catalog and product variants/barcodes.
4. POS, payments, returns and cash shifts.
5. Inventory ledger and purchasing.
6. Finance ledger and reconciliation.
7. Staff, customers and reporting.
8. Multi-branch synchronization and offline recovery.
9. AI advisory services.
10. Localization, hardening, end-to-end tests and release packaging.

## Security

Do not commit credentials, API tokens, private keys, signing keys, customer data, payment-card data, production database files, backups, logs, or environment files. Use GitHub Actions Secrets or an approved secret manager for deployment credentials.

Report suspected vulnerabilities privately to the repository owner. See [SECURITY.md](SECURITY.md).

## License

No license has been selected yet. Until one is added, the default copyright rules apply; do not assume the code is available for unrestricted reuse.
