# Session authentication and database access

## Implemented authentication lifecycle

Migrations `0005_restricted_session_lookup.sql` and
`0006_otp_sessions_csrf.sql` add a restricted pre-tenant session lookup,
OTP challenge functions, a CSRF digest on each session, and narrowly scoped
permissions. The `auth_session_lookup_owner` role is NOLOGIN and NOBYPASSRLS.
It can read only the required session and identity columns and access OTP
challenge rows through role-specific RLS policies. It cannot read tenant
business data, finance or procurement data. Runtime is not a member of this
owner role.

The OTP service:
- Generates a cryptographically random six-digit code and stores only an
  HMAC digest bound to the challenge ID.
- Uses an HMAC fingerprint for the identifier, a five-minute expiry, a
  60-second resend delay, at most five requests per hour, and at most five
  failed verification attempts per challenge.
- Serializes rate-limit checks per identifier with a transaction advisory lock.
- Returns the same public acceptance response for known and unknown identifiers.
- Requires an injected SMS/email delivery adapter; no provider credentials or
  production delivery integration are included in this repository.

Successful verification checks active identity, tenant and membership using
trusted database records, then issues a random opaque session token and a
separate random CSRF token. Only SHA-256 digests are persisted. The session
cookie is Secure, HttpOnly, SameSite=Strict and Path=/; the CSRF cookie is
Secure, readable by the client, SameSite=Strict and Path=/.

Session rotation revokes the current session and creates a linked successor in
one tenant-scoped transaction. Logout revokes the current session and clears
both cookies. Login, rotation, logout and session-resolution outcomes are
written to audit records.

For unsafe authenticated methods, the resolver requires the CSRF cookie and
`X-CSRF-Token` header to match, and verifies the supplied token against the
digest returned by the restricted SECURITY DEFINER lookup. Runtime never gets
direct SELECT access to `auth_sessions`. OTP request and verification routes
also require an exact same-origin `Origin` header.

After session lookup, the application opens a separate transaction using the
ordinary runtime role, sets transaction-local `app.tenant_id` and
`app.subject_id`, and loads active identity, tenant membership, role and
active branch memberships under forced RLS. Client-supplied tenant, role,
subject and branch claims are never trusted.

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
0005 grants execution of the restricted session lookup and revokes direct
SELECT on `auth_sessions`. Migration 0006 adds OTP and CSRF operations and
grants only the required runtime functions and session write permissions.
Production grants must remain narrow; do not copy the blanket grants used by
the disposable CI database.

## FastAPI wiring

Install the server extra and start the executable FastAPI host with the
restricted Runtime DSN:

```bash
pip install -e ".[server]"
export DATABASE_URL="postgresql://retail_runtime:<managed-secret>@<db-host>:5432/<db-name>"
uvicorn retail_app.main:app --host 0.0.0.0 --port 8000
```

The factory can mount OTP routes when an `AuthService` is supplied with an
SMS/email delivery implementation:

```python
from retail_app.api.host import create_app
from retail_app.infrastructure.database import PostgresDatabase
from retail_app.security.auth_service import AuthService

database = PostgresDatabase(runtime_dsn)
auth = AuthService(database, otp_hmac_secret=secret_bytes, otp_delivery=delivery_adapter)
app = create_app(database, auth_service=auth)
```

The default executable entrypoint intentionally does not configure a delivery
provider or OTP secret; therefore it does not expose OTP routes until the
operator supplies those dependencies through the host factory. Do not place
provider credentials or HMAC secrets in source control.

## Remaining production gates

- No SMS/email provider adapter, provider credentials, delivery retry queue or
  delivery observability are configured. OTP routes are opt-in through host
  dependency injection.
- Identifier recovery, multi-factor step-up, device management, session
  inventory/revoke-all, refresh-token reuse-family invalidation, and account
  recovery workflows are not included.
- The database column is still named `refresh_token_hash`; it currently stores
  the hash of the opaque session cookie. A dedicated access/session token
  schema should replace this legacy name before production.
- Same-origin checks require an exact `Origin` header; deployment behind a
  reverse proxy must preserve the correct external scheme and host.
- Do not deploy until a real delivery adapter is configured, provider
  credentials are stored in a secret manager, CI passes on the final commit,
  and an independent security review is complete.

## Migration and recovery boundary

No operational database migration has been run and no deployment has been
performed. CI applies migrations only to an ephemeral PostgreSQL service.
Production migration and rollback require a separate operator-reviewed change.

For rollback, first stop application traffic, revoke runtime EXECUTE on the
new OTP/session functions, remove only the newly added policies/functions and
CSRF column after confirming no active application depends on them, and retain
existing session records. Do not drop or truncate existing authentication
records as part of rollback. Restore from a verified backup only if schema
rollback is insufficient.
