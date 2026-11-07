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
- **Central database:** PostgreSQL, accessed through SQLAlchemy 2.x.
- **Migrations:** Alembic; schema changes must be versioned and reviewed.
- **Local/offline mode:** SQLite on a single local node, with an application-level synchronization protocol. Never share a SQLite database file over a network filesystem.
- **API:** versioned REST endpoints under `/api/v1`.
- **Financial and inventory records:** append-only ledgers; corrections use reversal or adjustment entries.
- **Multi-tenancy:** tenant-scoped data access and authorization checks at service boundaries; implementation is pending.
- **AI:** provider-independent interfaces; AI suggestions are advisory and sensitive actions require authorized human approval.

## Current implementation status

Implemented in the foundation branch:
- FastAPI application factory and versioned health endpoint.
- Environment-based application and optional database configuration.
- SQLAlchemy engine/session foundation with lazy connection behavior.
- Alembic migration environment.
- SQLite database unit test and PostgreSQL connectivity integration smoke test.
- CI matrix for Python 3.11/3.12 with a PostgreSQL 16 service.

Not implemented yet:
- Identity, login/session management, RBAC, tenant models and tenant isolation.
- Product, inventory, POS, procurement, CRM, ERP, payment integrations, offline synchronization, AI modules, desktop/mobile packaging.

A documented or planned capability is not evidence that it is implemented or production-ready. No production deployment or release is declared.

## Development

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run unit tests:

```bash
pytest
ruff check .
```

Configure `DATABASE_URL` before running migrations. Example:

```bash
export DATABASE_URL='postgresql+psycopg://app:password@localhost:5432/ai_business_studio'
alembic upgrade head
```

Do not run migrations against production without a reviewed migration, verified backup, and a tested rollback/recovery plan.

## Security

Do not commit credentials, API tokens, private keys, signing keys, customer data, payment-card data, production database files, backups, logs, or environment files. Use GitHub Actions Secrets or an approved secret manager for deployment credentials.

Report suspected vulnerabilities privately to the repository owner. See [SECURITY.md](SECURITY.md).

## License

No license has been selected yet. Until one is added, the default copyright rules apply; do not assume the code is available for unrestricted reuse.
