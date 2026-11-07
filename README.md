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
- **Multi-tenancy:** tenant-scoped data access and authorization checks at service boundaries; only identity membership foundations are currently implemented.
- **AI:** provider-independent interfaces; AI suggestions are advisory and sensitive actions require authorized human approval.

## Current implementation status

Implemented in the foundation branch:
- FastAPI application factory and versioned health endpoint.
- Environment-based application and optional database configuration.
- SQLAlchemy engine/session foundation with lazy connection behavior.
- Initial identity schema for tenants, users, memberships, tenant roles, permissions, sessions, and audit events.
- Argon2 password hashing and opaque session-token digest primitives.
- Identity service primitives for normalized-email registration, credential verification, session creation/lookup/revocation, and tenant-checked role assignment.
- Database-enforced tenant consistency for membership-role assignments using composite foreign keys.
- Case-insensitive unique email index enforced by the database.
- Initial Alembic revision (`0001_identity`).
- HTTP authentication endpoints: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, and `POST /api/v1/auth/logout`.
- Browser session cookies are HttpOnly, SameSite=Lax, configurable Secure, and contain opaque tokens; only token digests are stored.
- Session-bound CSRF tokens are stored as digests and exposed in a separate readable SameSite=Lax cookie; unsafe authentication requests require a matching `X-CSRF-Token` header.
- Public self-registration is disabled by default and requires explicit environment configuration.
- Successful registration/login and denied login audit events; persistent, database-backed login throttling keyed by an HMAC of normalized email and client IP; API tests for cookie/session lifecycle, CSRF rejection, invalid credentials, and lockout.
- SQLite identity tests and PostgreSQL integration smoke test.
- CI matrix for Python 3.11/3.12 with a PostgreSQL 16 service and strict pytest warnings.

Not implemented and still required before production use:
- Trusted-origin enforcement, MFA, account recovery, and expanded abuse monitoring. Production deployments must set a strong unique `AUTH_RATE_LIMIT_SECRET`.
- Persistent login rate limiting, lockout policy, failed-attempt monitoring, MFA, and account recovery.
- Complete RBAC permission evaluation and enforcement on tenant-scoped business endpoints.
- Database-enforced append-only audit controls.
- Product, inventory, POS, procurement, CRM, ERP, payment integrations, offline synchronization, AI modules, desktop/mobile packaging.

The authentication API is an incremental foundation, not a production-ready security boundary. Do not expose it to real customer data or public production traffic until the remaining security gates are implemented and independently verified. A documented or planned capability is not evidence that it is implemented.

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
