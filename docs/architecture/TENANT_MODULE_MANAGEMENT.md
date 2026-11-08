# Tenant subscriptions and module activation

Status: **Implemented in the feature branch; pending CI and review**

## Persistent model

- One `tenant_subscriptions` row per tenant stores edition and active/suspended status.
- One `tenant_module_entitlements` row per tenant/module stores entitlement source, entitlement status and enabled status.
- Unique tenant constraints prevent duplicate subscriptions and duplicate module records.
- Migration `0015_tenant_module_entitlements` backfills existing tenants to Starter and its five initial modules.
- New tenant registration provisions Starter entitlements in the same database transaction as identity creation.

## API contract

All endpoints require a signed-in tenant member and the tenant context header `X-Tenant-ID`.

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/api/v1/modules` | `modules.read` | View edition and module entitlements |
| GET | `/api/v1/modules/editions` | `modules.read` | List edition bundle definitions |
| PUT | `/api/v1/modules/edition` | `modules.manage` + CSRF | Change the tenant edition |
| PUT | `/api/v1/modules/{module_id}` | `modules.manage` + CSRF | Enable or disable an entitled module |

The owner system role receives module administration permissions. Custom roles may be granted them through the existing role permission workflow.

## Runtime enforcement

Protected API routes use `require_module(module_id, permission_code)`. The dependency checks, on every request:
1. authenticated user and active tenant membership;
2. tenant-scoped RBAC permission;
3. active tenant subscription;
4. module release lifecycle (planned modules fail closed);
5. module entitlement and enabled state;
6. all transitive dependencies are entitled and enabled.

The procurement preview endpoint is the first route migrated to this guard. Other module APIs must adopt it as they are implemented.

## Edition changes and data safety

- Edition changes recompute the edition entitlement set transactionally and write an append-only audit event.
- Modules not included in a downgraded edition are disabled and lose entitlement; historical records are not deleted.
- Planned modules may be included as future bundle targets but remain disabled and non-activatable until released.
- Preview modules may be enabled only when entitled and all dependencies are active.
- Disabling a dependency is rejected while any dependent module remains enabled.
- Module activation changes require CSRF protection and tenant-scoped `modules.manage`.

## Explicit limitations

- Edition changes are administrative entitlement changes, not payment-confirmed purchases.
- Add-on purchasing, payment gateway verification, billing, proration, renewal and expiry are not implemented.
- The module catalog is currently static Python metadata; signed external manifests and runtime plugin loading are future work.
- Only the procurement preview route currently enforces module entitlements. Every future module route and background job must use equivalent checks.
- Existing tenant data is preserved, but this phase does not implement a module-specific archival/export workflow.

## Acceptance tests

- New registration receives Starter and expected initial entitlements.
- Growth upgrade entitles procurement but leaves planned sales disabled.
- Tenant A cannot inspect or change tenant B's subscription.
- Planned modules cannot be enabled.
- A dependency cannot be disabled while a dependent module is enabled.
- Disabling a module preserves entitlement but blocks new route access.
- A suspended subscription blocks protected module routes and management changes.
