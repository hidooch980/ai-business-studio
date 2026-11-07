# AI Business Studio

A modular business operations platform for retail and multi-branch businesses in Iran and international markets.

## Product direction

AI Business Studio is planned as an offline-capable platform with shared business data across POS, inventory, procurement, CRM, ERP, finance, payments, reconciliation, and AI-assisted reporting.

## Architecture decisions

- **Backend:** Python and FastAPI.
- **Architecture:** modular monolith with explicit domain boundaries and versioned contracts.
- **Central database:** PostgreSQL, accessed through SQLAlchemy 2.x.
- **Migrations:** Alembic; schema changes must be versioned and reviewed.
- **Local/offline mode:** SQLite on a single local node, with an application-level synchronization protocol. Never share a SQLite database file over a network filesystem.
- **API:** versioned REST endpoints under `/api/v1`.
- **Financial and inventory records:** append-only ledgers; corrections use reversal or adjustment entries.
- **Multi-tenancy:** tenant-scoped data access and authorization checks at service boundaries; identity and the initial product catalog are implemented, but not all business domains.
- **AI:** provider-independent interfaces; AI suggestions are advisory and sensitive actions require authorized human approval.

## Current implementation status

Implemented in the foundation branch:
- FastAPI application factory and versioned health endpoint.
- Environment-based application and optional database configuration.
- SQLAlchemy engine/session foundation with lazy connection behavior.
- Initial identity schema for tenants, users, memberships, tenant roles, permissions, sessions, and audit events.
- Argon2 password hashing and opaque session-token digest primitives.
- Identity service primitives for normalized-email registration, credential verification, session creation/lookup/revocation, and tenant-checked role assignment.
- Database-enforced tenant consistency for membership-role assignments and invitation-role references using composite foreign keys.
- Case-insensitive unique email index enforced by the database.
- Versioned Alembic migrations `0001_identity` through `0010_transactional_outbox`, including `0009_financial_accounts`, covering identity, CSRF digests, persistent login throttling, append-only audit events, tenant invitations, the financial journal, and product catalog.
- HTTP authentication endpoints: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, and `POST /api/v1/auth/logout`.
- Tenant-scoped invitation lifecycle: create, list, resend with token rotation, revoke, and one-time acceptance; create/resend actions share a 20-per-hour tenant limit; email delivery remains manual until a provider is configured.
- Tenant-scoped RBAC APIs for roles, permissions, memberships, and membership-role assignment/removal, with CSRF protection and last-active-owner safeguards.
- Tenant-scoped product catalog API: create, list/search, update and soft-deactivate products; tenant-unique SKU/barcode constraints; catalog-specific permissions and audit events.
- Tenant-scoped inventory foundation: warehouse management, append-only receipt/issue/adjustment movements, idempotency keys, non-negative stock protection, database-maintained balance projections, tenant-composite foreign keys and SQLite/PostgreSQL immutability triggers.
- Durable transactional outbox foundation: inventory movement events are committed atomically with stock changes; tenant deduplication, SQLite atomic claims, PostgreSQL skip-locked claims, expiring worker leases, retry scheduling and dead-letter state are implemented. A continuously running dispatcher and provider adapters are not yet deployed.
- Durable transactional outbox foundation: tenant-scoped event deduplication, event enqueue in the inventory movement transaction, worker leases, stale-lease protection, retry scheduling and dead-letter state.
- Tenant-scoped chart-of-accounts API with typed asset/liability/equity/income/expense accounts, same-type parent hierarchy, tenant-safe composite foreign keys, duplicate-code protection and guarded deactivation. Journal lines are not yet linked to account IDs.
- Append-only tenant-scoped double-entry journal foundation: integer minor-unit amounts, per-entry debit/credit balancing, idempotency keys, one-time balanced reversals, tenant-scoped journal listing, audit events, and SQLite/PostgreSQL mutation and overposting guards.
- Browser session cookies are HttpOnly, SameSite=Lax, configurable Secure, and contain opaque tokens; only token digests are stored.
- Authenticated users can list their own recent sessions and revoke individual sessions, including the current session; revocation is CSRF-protected and audited.
- Session-bound CSRF tokens are stored as digests and exposed in a separate readable SameSite=Lax cookie; unsafe authentication requests require a matching `X-CSRF-Token` header and same-host Origin/Referer validation when those headers are present.
- Public self-registration is disabled by default and requires explicit environment configuration.
- Successful registration/login and denied login audit events; persistent, database-backed login throttling keyed by an HMAC of normalized email and client IP (default 8 failures per 5 minutes, 15-minute lock); production requires a unique `AUTH_RATE_LIMIT_SECRET` of at least 32 characters.
- Database-enforced append-only audit events using SQLite and PostgreSQL triggers; migration tests verify that updates and deletes are rejected, and PostgreSQL additionally rejects table truncation. Production database roles must not own the schema or have DDL privileges.
- SQLite identity/migration tests and PostgreSQL 16 integration tests, including concurrent last-active-owner deactivation protection.
- CI matrix for Python 3.11/3.12 with PostgreSQL 16, strict pytest warnings, Ruff, dependency vulnerability audit, Compose validation, and a production Docker image build.
- Container deployment foundation: non-root application image, read-only runtime filesystem, local-only port binding, PostgreSQL storage, and separate application/migration database roles. See [container deployment](docs/deployment/CONTAINER.md).
- Encrypted PostgreSQL backup and guarded restore utilities with SHA-256 verification, explicit restore confirmation and single-transaction restore. See [backup and restore runbook](docs/deployment/BACKUP_RESTORE.md); scheduled off-host backups and a real restore rehearsal remain outstanding.
- Production configuration rejects SQLite/missing DATABASE_URL and insecure session cookies; SQLite foreign-key enforcement is enabled per connection.
- CI runs a Python dependency vulnerability audit, Compose validation and Docker build after the test/lint stages.

Not implemented and still required before production use:
- MFA, account recovery, device metadata/fingerprinting, expanded abuse monitoring, and centralized administrator session controls.
- API-wide IP/account rate limits; invitation create/resend currently has a per-tenant 20-per-hour limit.
- Independent production security review and additional PostgreSQL concurrency stress tests for role and invitation operations.
- Complete accounting domain: link journal lines to chart accounts, posting periods, adjustment workflows, reconciliation, tax rules, multi-currency FX handling, and financial reporting.

- Product categories/unit conversion, batch/expiry tracking, stock valuation, POS, procurement, sales, CRM, notification delivery/worker processes, broader ERP workflows, payment integrations, offline synchronization, AI modules, desktop/mobile packaging.

The API and ledger are incremental foundations, not a production-ready financial or security boundary. The journal API supports one-time compensating reversals but does not yet provide a chart of accounts, posting periods, reconciliation, FX conversion, tax handling, or financial statements. Do not expose it to real customer data or public production traffic until the remaining security and accounting controls are implemented and independently verified. A documented or planned capability is not evidence that it is implemented.

## Development

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run unit tests and lint:

```bash
pytest
ruff check .
```

Configure `DATABASE_URL` before running migrations:

```bash
export DATABASE_URL='postgresql+psycopg://app:password@localhost:5432/ai_business_studio'
alembic upgrade head
```

Authentication configuration is documented in `.env.example`. Keep public registration disabled unless an intentional onboarding flow is in place. Set `SESSION_COOKIE_SECURE=true` behind HTTPS.

Do not run migrations against production without a reviewed migration, verified backup, and tested recovery plan.

## Security

Do not commit credentials, API tokens, private keys, signing keys, customer data, payment-card data, production database files, backups, logs, or environment files. Use GitHub Actions Secrets or an approved secret manager for deployment credentials.

Report suspected vulnerabilities privately to the repository owner. See [SECURITY.md](SECURITY.md).

## License

No license has been selected yet. Until one is added, the default copyright rules apply; do not assume the code is available for unrestricted reuse.
