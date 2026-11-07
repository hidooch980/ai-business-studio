# AI Business Studio

A modular business operations platform for retail and multi-branch businesses in Iran and international markets.

## Product direction

AI Business Studio is planned as an offline-capable platform with shared business data across:

- Point of sale (POS), products, barcode/QR and sales
- Inventory, warehouses, batches and expiry management
- Procurement and supplier management
- CRM, customer support and loyalty
- ERP, finance and accounting workflows
- Payment provider integrations and reconciliation
- AI-assisted analytics, forecasting and management reporting

## Architecture decisions

- **Backend:** Python and FastAPI.
- **Architecture:** modular monolith with explicit domain boundaries and versioned contracts.
- **Central database:** PostgreSQL.
- **Local/offline mode:** SQLite on a single local node, with an application-level synchronization protocol. Never share a SQLite database file over a network filesystem.
- **API:** versioned REST endpoints under `/api/v1`.
- **Financial and inventory records:** append-only ledgers; corrections use reversal or adjustment entries.
- **Multi-tenancy:** tenant-scoped data access and authorization checks at service boundaries.
- **AI:** provider-independent interfaces; AI suggestions are advisory and sensitive actions require authorized human approval.

## Repository status

This repository is being bootstrapped. A documented architecture or planned capability is not evidence that the feature is implemented or production-ready. See the project documentation and CI results as implementation progresses.

## Development

The initial foundation will establish:

1. Application factory and health endpoint
2. Configuration through environment variables
3. Automated tests and CI
4. Security and contribution baselines
5. Domain modules introduced incrementally behind tested contracts

## Security

Do not commit credentials, API tokens, private keys, signing keys, customer data, payment-card data, production database files, backups, logs, or environment files. Use GitHub Actions Secrets or an approved secret manager for deployment credentials.

Report suspected vulnerabilities privately to the repository owner. See [SECURITY.md](SECURITY.md).

## License

No license has been selected yet. Until one is added, the default copyright rules apply; do not assume the code is available for unrestricted reuse.
