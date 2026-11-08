# Session bootstrap and RLS-safe authentication

## Purpose

The normal `auth_sessions` RLS policy requires both `app.tenant_id` and
`app.subject_id`. Those values are not known until a cookie token is resolved.
Do not weaken that policy, add a runtime BYPASSRLS grant, or grant the runtime
role direct access to the bootstrap table.

## Narrow bootstrap design (migration 0005)

Before applying migration 0005, provision a dedicated role:

```sql
CREATE ROLE auth_bootstrap_owner NOLOGIN NOBYPASSRLS;
```

The migration creates `auth_session_bootstrap`, a minimal lookup table containing
only the token digest, session/tenant/identity identifiers, expiry and revocation
state. A SECURITY DEFINER trigger function mirrors session insert/update/delete
inside the same transaction. A second SECURITY DEFINER function accepts the
server-computed token digest and returns identifiers only for an unexpired,
non-revoked session.

Both functions are owned by `auth_bootstrap_owner`, which is NOLOGIN and
NOBYPASSRLS. Its only elevated capability is ownership/privileges on this narrow
bootstrap table. It does not own `auth_sessions`, `identities`, memberships or
tenant data. The runtime role receives EXECUTE on the lookup function only;
it receives no SELECT/INSERT/UPDATE/DELETE on the bootstrap table. The function
uses a fixed search_path and schema-qualified table reference.

The migration assumes the runtime database role is named `app_runtime`. If
deployment uses another role, adjust the GRANT target in a reviewed migration
before rollout; do not grant to PUBLIC.

## Request algorithm

1. Read the opaque session token only from the HttpOnly, Secure, SameSite cookie.
   Reject missing, malformed or oversized values. Never accept a tenant, subject,
   role or branch from request headers/body/query parameters.
2. Compute SHA-256 (or the token format's specified digest) in application code.
   Store and compare only the digest; never log the raw cookie.
3. In a short transaction, call
   `SELECT tenant_id, identity_id, session_id FROM resolve_auth_session_bootstrap(%s)`.
   No row means invalid, expired or revoked session. This function does not
   establish authorization and returns no role or branch information.
4. In the same transaction, set `app.tenant_id` and `app.subject_id` with
   transaction-local `set_config(..., true)` using only the returned UUIDs.
5. Under the ordinary RLS policies, load the session row, identity and current
   tenant membership. Require session ID/hash match, unexpired and not revoked,
   identity active, tenant active, membership active. Read role from the current
   membership row, never from cookie claims or bootstrap data.
6. Resolve branch membership from current `branch_memberships`. Enforce
   branch scope in the service query/policy; no branch membership means no
   branch-scoped access.
7. Build the immutable AccessContext from these database rows and execute all
   protected reads/writes in this same transaction. Transaction-local settings
   are cleared automatically at transaction end; never split context setup and
   protected work across pooled connections.

## Security boundaries

- `auth_bootstrap_owner` must remain NOLOGIN and NOBYPASSRLS.
- `app_runtime` must not own RLS tables and must not be SUPERUSER or BYPASSRLS.
- Runtime cannot read the bootstrap table directly; only EXECUTE is granted.
- No SECURITY DEFINER function may return role, branch list, PII, token digest or
  arbitrary session metadata.
- The trigger mirror is transactionally consistent with `auth_sessions`.
  Reconcile it periodically and fail closed if lookup and authoritative row differ.
- A missing row, DB error, malformed cookie, inactive identity, revoked membership
  or ambiguous lookup must deny access.
- Use TLS, secure cookie flags, bounded cookie size, token rotation and secret
  redaction. Do not put bearer tokens in URLs.
- This migration is additive and is not an instruction to apply it to production.
  CI must validate it against PostgreSQL 16 before any rollout. Back up and test
  restore before a controlled production migration.

## Operations: installation, backup and restore

1. Provision the NOLOGIN/NOBYPASSRLS owner and least-privilege runtime role.
2. Apply migrations in order using the schema-owner account, never the runtime
   account. Verify grants and role attributes afterward.
3. Set cookie secrets through the deployment secret manager; do not commit
   DSNs, peppers or cookie signing keys.
4. Back up with a consistent PostgreSQL custom-format dump, including schema and
   data; protect it with encryption and access controls. Keep WAL/PITR backups
   if the recovery objective requires point-in-time restore.
5. Restore into an isolated database first, verify migrations, role ownership,
   grants, RLS policies, bootstrap/session row consistency and application
   health, then plan a controlled cutover.
6. Never restore a production dump into CI or a developer environment without
   sanitization. Record backup time, PostgreSQL major version and restore-test
   result.

## Validation required before merge

Add PostgreSQL integration tests for valid lookup, unknown digest, expiry,
revocation, inactive identity, revoked/suspended membership, role changes,
cross-tenant access, branch membership removal, transaction rollback consistency,
connection-pool context reset, and proof that app_runtime cannot SELECT the
bootstrap table or bypass RLS. The migration must run only in ephemeral CI.
