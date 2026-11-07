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

1. Add SQLAlchemy, Alembic, PostgreSQL driver, and validated database settings.
2. Add a migration environment and an initial metadata baseline.
3. Add tenant, user, membership, role, permission, and session models.
4. Implement authentication and authorization services.
5. Add tenant-isolation and privilege-escalation regression tests.
6. Add PostgreSQL service integration to CI.
7. Add migration upgrade tests and backup/restore rehearsal.

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
