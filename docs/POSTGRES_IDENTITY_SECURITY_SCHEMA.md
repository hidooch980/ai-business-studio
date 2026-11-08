# PostgreSQL Identity and Security Schema

Status: migration is exercised in CI against an ephemeral PostgreSQL 16 service by seven RLS integration checks. It has **not** been applied to a live/customer database.

## Migration

Apply `migrations/0001_identity_security.sql` using a dedicated schema-owner role during a controlled migration window. The application role must not own these tables and must not have SUPERUSER or BYPASSRLS. Grant only required table/sequence/function privileges after reviewing each service's needs.

The migration creates tenants, branches, identities, tenant and branch memberships, sessions, OTP challenges and security audit events. It stores only OTP HMAC and refresh-token hash fields, never plaintext credentials. OTP challenge rows support purpose, expiry, single-use consumption, invalidation and bounded attempts; this schema alone does not implement OTP generation, delivery, verification or throttling.

## Transaction context contract

After validating a session and loading current active membership from trusted records, the API must set `app.tenant_id` and `app.subject_id` with transaction-local settings (for example `SET LOCAL`). Never copy these values from client-supplied tenant, role or branch fields. Use a single database transaction for context setup and protected queries; connection-pool reuse must not leak context between requests.

RLS is defense in depth, not a replacement for service authorization. Branch-scoped queries must still check active `branch_memberships`; customer queries must still enforce ownership. PostgreSQL table owners and roles with BYPASSRLS can bypass policies, so runtime roles and migration ownership must be separated. Audit records must be append-only at the application privilege layer.

## Important integration caveats

- CI applies the migration to an ephemeral PostgreSQL 16 database and runs seven integration checks. This validates the CI target version, not the production database or deployment environment.
- `identities` is global and deliberately uses a self-or-tenant-membership policy rather than a tenant_id column.
- The OTP fingerprint and code HMAC require separate, high-entropy server-side peppers from a secret manager.
- Rate limiting by IP/device/global provider spend belongs in a dedicated service or shared limiter, not only in this schema.
- Session refresh rotation and reuse detection require transactional application logic.
- No FastAPI routes, ORM, migration runner, provider adapter, or live DB connection are added by this migration.
- Do not expose database credentials to the frontend. Never grant clients direct access to the application database.

## Rollout checks

1. Create separate migration-owner and runtime roles; verify runtime role has no ownership, SUPERUSER or BYPASSRLS.
2. Review the PostgreSQL 16 CI results; repeat the migration and cross-tenant, cross-branch and cross-user checks on the intended production PostgreSQL major version.
3. Verify missing transaction context returns no rows and cannot insert scoped rows; anonymous OTP challenges additionally require the trusted transaction-local `app.otp_onboarding=true` flag.
4. Test connection-pool reuse to prove transaction-local settings are cleared.
5. Add least-privilege grants, backup/restore and migration rollback procedures.
6. Only then connect the FastAPI identity/session repositories and OTP provider.
