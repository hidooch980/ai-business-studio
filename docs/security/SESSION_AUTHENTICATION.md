# Session authentication and database access

## Current implementation boundary

Migration `0005_restricted_session_lookup.sql` adds a single-purpose PostgreSQL
function for locating a session by SHA-256 token hash before tenant context is
known. The function is `SECURITY DEFINER`, has a fixed search path, returns no
token hash, and is executable only by the configured runtime role.

The function owner is a NOLOGIN role without BYPASSRLS. A role-specific RLS
policy permits it to SELECT only the six required columns of `auth_sessions`;
a second role-specific policy permits INSERT only into
`auth_session_lookup_audit`. It cannot read that audit table and has no
privileges on identities, tenants, memberships, finance, procurement, or other
tables. Runtime is not a member of that owner role and must not be granted
membership in it.

The lookup function checks revocation and expiry using PostgreSQL's clock and
records `matched`, `unknown`, `expired`, or `revoked` outcomes without
storing token material. After a valid lookup, the application opens a separate
transaction using the ordinary runtime role, sets transaction-local
`app.tenant_id` and `app.subject_id`, and loads active identity, tenant
membership, role and active branch memberships under existing forced RLS
policies. Successful and denied membership resolution is recorded in the
tenant-scoped `security_audit_events` table. Client-supplied tenant, role,
subject and branch values are never consulted.

## Runtime role provisioning

Before applying migrations, provision a non-owner application role. It must not
own protected tables, must not be SUPERUSER or BYPASSRLS, and must not be a
member of `auth_session_lookup_owner`. Example (choose a unique secret through
your secret manager; do not commit it):

```sql
CREATE ROLE retail_runtime LOGIN PASSWORD '<managed-secret>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO retail_runtime;
```

Apply numbered migrations using a separate schema-owner connection. Migration
0005 grants the runtime role EXECUTE on the lookup function and revokes direct
SELECT on `auth_sessions`. Grant only the business-table privileges required
by the deployed application; do not use blanket table grants in production.

## FastAPI wiring

Create the database adapter from a secret-managed DSN and expose the factory:

```python
from retail_app.api.host import create_app
from retail_app.infrastructure.database import PostgresDatabase

app = create_app(PostgresDatabase(os.environ["DATABASE_URL"]))
```

The session cookie must be opaque, random, at least 32 characters, and set by
the future login service with Secure, HttpOnly, SameSite=Strict and Path=/.
The `__Host-` prefix additionally requires Secure and no Domain attribute.
The resolver validates expiry and revocation using PostgreSQL's clock, records those outcomes, and accepts only that cookie; it does not accept bearer tokens,
tenant headers, role headers, or request-body claims.

## Important limitations

- This is a session validator and FastAPI host integration, not a complete
  authentication product.
- OTP challenge verification, delivery providers, login throttling, session
  creation, refresh rotation, logout endpoint, CSRF strategy for state-changing
  cookie-authenticated requests, and recovery flows remain unimplemented.
- The current database column is named `refresh_token_hash`; the resolver uses
  it as the opaque session cookie credential. Rename/rework this schema when
  the access/refresh-token lifecycle is implemented, before production.
- Do not deploy this host until cookie issuance, CSRF protection, rate limiting,
  audit persistence, and a full security review are complete.

## Install, migrate, rollback and recovery

1. Back up the database and verify a restore to a separate database.
2. Create the runtime role as above; keep the schema-owner DSN separate.
3. Apply migrations with the repository migration runner and schema-owner DSN.
4. Deploy the application with the restricted runtime DSN.
5. Verify the runtime role cannot directly SELECT from `auth_sessions`, cannot
   SET ROLE to `auth_session_lookup_owner`, and can execute only the session
   lookup function.
6. Run the PostgreSQL integration tests and the application health check.

Migration 0005 is additive. To roll back the feature, first stop application
traffic, then as schema owner revoke EXECUTE from the runtime role, drop
`public.resolve_auth_session(bytea)`, revoke the column grants, and drop
`auth_session_lookup_owner` only after confirming it owns no other objects.
Do not drop or truncate existing session records as part of rollback. Restore
from the verified backup only if schema rollback is insufficient. Production
migration and rollback must be operator-reviewed; CI tests do not authorize
production changes.
