# Foundation Next: Database and Identity

## Scope

The next implementation increment establishes persistence and identity primitives before business modules are added.

## Decisions

- PostgreSQL is the authoritative central multi-user database.
- SQLAlchemy 2.x is the ORM and Alembic manages schema migrations.
- SQLite is limited to a single local node; multiple tills communicate with a local service over LAN.
- Tenant identity is derived from the authenticated server-side principal, never trusted from an arbitrary request body or header.
- Every tenant-owned query and mutation must enforce tenant scope.
- Passwords are stored using a modern password hashing scheme; plaintext and reversible password storage are prohibited.
- Sessions use secure, HttpOnly cookies with CSRF protection for browser-based state-changing requests.
- Authorization is deny-by-default and checked at the service boundary.
- Audit records capture actor, tenant, action, target, timestamp, correlation ID, and outcome without logging secrets.

## Delivery sequence

Completed in the current foundation branch:
1. SQLAlchemy, Alembic, PostgreSQL driver, validated database settings, and PostgreSQL CI service.
2. Initial identity schema and versioned migrations, including session CSRF digests and persistent login rate-limit state.
3. Argon2 identity primitives, cookie-based register/login/me/logout endpoints, session revocation, CSRF double-submit validation, same-host Origin/Referer checks, and persistent lockout.
4. Regression tests for cross-tenant role assignment, credential failures, session lifecycle, CSRF rejection, lockout, and migration upgrade/downgrade.

Remaining delivery sequence:
1. Implement deny-by-default RBAC permission evaluation and FastAPI authorization dependencies.
2. Enforce tenant scope on every business read/write and test cross-tenant access attempts.
3. Strengthen audit append-only guarantees at the database layer.
4. Add MFA, recovery flows, session/device management, and backup/restore rehearsal.
5. Perform security review and production deployment rehearsal before real customer data is permitted.

## Exit criteria

- Fresh PostgreSQL database can be migrated to head.
- Existing supported schema can be upgraded without data loss.
- Unauthenticated requests cannot access protected endpoints.
- A user cannot read or mutate another tenant's records by changing identifiers.
- Revoked memberships and sessions stop granting access.
- All security-sensitive actions generate auditable events.
- CI executes both unit tests and PostgreSQL integration tests.

## Explicit non-goals

This increment does not connect to live banks, PSPs, card terminals, tax services, or AI providers. Those integrations require separately verified contracts, credentials, sandbox evidence, and production authorization.
