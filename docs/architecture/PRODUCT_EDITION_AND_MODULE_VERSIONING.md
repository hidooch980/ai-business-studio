# Product editions, modular packaging and versioning policy

Status: **Approved product architecture; module registry implementation is an initial catalog only**

## 1. Product packaging model

AI Business Studio is one modular product, not a collection of disconnected editions. Every customer has a product edition, explicit module entitlements, optional add-ons, tenant-level feature configuration and role permissions.

- Product edition determines the default bundle and support envelope.
- A module is an independently versioned business capability with declared dependencies.
- An add-on is an independently licensable optional module.
- A feature flag controls staged rollout or a beta feature; it is not a substitute for entitlement or permission.
- Tenant entitlement is persisted server-side and checked for every protected operation. Hiding a menu item is never authorization.
- A module's lifecycle status is explicit: foundation, preview, or planned. Planned modules cannot be activated merely because an edition lists them.

The current Python registry is a catalog/entitlement preview. It does not yet persist subscriptions, bill customers, activate tenant modules, or enforce runtime entitlements.

## 2. Proposed product editions

The edition names and bundles are proposed packaging defaults. Commercial pricing, usage limits and contractual SLAs are intentionally not hard-coded.

| Capability | Starter | Growth | Business | Enterprise |
|---|---|---|---|---|
| Core identity, roles, audit | Included | Included | Included | Included |
| Product catalog and inventory foundation | Included | Included | Included | Included |
| Finance foundation and standard reports | Included | Included | Included | Included |
| Smart procurement | — | Preview/add-on until released | Included after release | Included after release |
| Sales and order management | — | Planned bundle | Included after release | Included after release |
| Smart POS | — | Planned bundle | Included after release | Included after release |
| CRM and loyalty | — | Planned bundle | Included after release | Included after release |
| Workflow and approvals | Basic | Expanded | Advanced | Advanced |
| Treasury and cash management | — | Add-on | Included after release | Included after release |
| HR and payroll | — | Add-on | Included after release | Included after release |
| AI analytics and forecasting | Basic reports | Add-on/preview | Included after release | Advanced after release |
| Multi-company and consolidation | — | — | Add-on | Included after release |
| External integrations and public API | Limited | Standard after release | Expanded after release | Advanced after release |
| Manufacturing, quality, assets, logistics, portals | Optional add-ons | Optional add-ons | Optional add-ons | Optional add-ons |

**Important:** "Included after release" is a target bundle, not a claim that the module is already production-ready. The registry status is the source for current implementation readiness.

## 3. Module catalog and dependency model

| Module ID | Capability | Dependencies | Current implementation status |
|---|---|---|---|
| platform | Identity, tenant, permissions, audit | — | Foundation |
| catalog | Products/services, SKU and barcode | platform | Foundation |
| inventory | Warehouses and stock ledger | catalog | Foundation |
| finance | Journals, accounts and periods | platform | Foundation |
| reports | Operational/financial reports | platform | Preview |
| procurement | Supplier and demand-driven purchasing | catalog, inventory, finance | Preview |
| sales | Quotes, orders, invoices and customer balances | catalog, inventory, finance | Planned |
| pos | Cashier, shifts, tender and receipts | sales, inventory, finance | Planned |
| crm | Customer history, loyalty and service | platform, sales | Planned |
| workflows | Approvals and automation | platform | Preview |
| treasury | Cash, bank and liquidity | finance | Planned |
| hr_payroll | Employees, attendance and payroll | platform, finance | Planned |
| analytics_ai | Forecasting, BI and anomaly detection | reports | Planned |
| integrations | Provider adapters and public API | platform | Planned |
| multi_company | Legal entities and consolidation | platform, finance | Planned |
| manufacturing | BOM, MRP, work orders and WIP | catalog, inventory, finance | Optional / planned |
| quality_assets | Quality, fixed assets and maintenance | inventory, finance | Optional / planned |
| service_logistics | Service desk, fleet and logistics | platform, inventory | Optional / planned |
| portals | Customer and supplier self-service | platform, integrations | Optional / planned |

Dependencies are declared by stable module ID, never by display name. The resolver includes dependencies for a dependency preview but does not silently turn them into paid add-ons. Activation requires a compatible, released module and all dependency entitlements.

## 4. Versioning rules

Use independent version axes; do not overload one version number:

1. **Product release:** Semantic Versioning `MAJOR.MINOR.PATCH`.
   - MAJOR: incompatible product behavior, supported upgrade path or public contract.
   - MINOR: backward-compatible modules/features.
   - PATCH: backward-compatible fixes and security updates.
2. **Module release:** each module has its own SemVer and compatibility declaration. A module may ship independently only when its dependencies and host platform range are satisfied.
3. **Public API:** versioned path such as `/api/v1`. Breaking changes create `v2`; additive fields and endpoints remain backward-compatible within v1.
4. **Database schema:** monotonic Alembic migration revisions, independent from product/module versions. Never reuse or rewrite a migration that has shipped.
5. **AI model:** separate model ID, model version, training-data window, feature schema, evaluation metrics and rollback pointer.
6. **Client applications:** Android, web and desktop clients carry their own release number and minimum compatible API version.

Initial product version remains `0.1.0` until a supported production release is approved. Pre-1.0 releases may change contracts, but migration notes and release notes are still mandatory.

## 5. Module package contract

Every module must provide:
- Stable module ID, display name, module SemVer, lifecycle status and owner.
- Required platform range and dependency IDs/ranges.
- Declared routes, permissions, events, settings and background jobs.
- Database migrations owned by that module and reversible/forward-recovery notes.
- Data retention, export and tenant-isolation rules.
- Feature flags, configuration schema and secret requirements.
- Health/readiness checks, metrics and structured audit actions.
- Unit, API, authorization, migration, integration and upgrade tests.
- Documentation, localization keys and accessibility requirements.

Modules may communicate through documented service interfaces and versioned domain events/outbox contracts. A module must not write directly to another module's tables. Core shared contracts remain small and stable.

## 6. Safe enable/disable and upgrade behavior

- Enable only after entitlement, dependency, compatibility and permission checks pass.
- Disabling a module stops new writes and background jobs, but does not delete historical business records.
- Re-enabling restores access without data recreation.
- Uninstall/data deletion is a separate privileged, audited retention workflow; it is never implied by disabling.
- Migrations use expand-and-contract: add compatible schema first, deploy code that supports old/new shape, backfill, verify, then remove obsolete columns only in a later major-safe release.
- Before upgrade: backup, checksum, migration dry run, restore rehearsal, tenant compatibility scan and rollback/forward-recovery plan.
- Never run destructive data migrations as a side effect of a user clicking "disable module".

## 7. Entitlement and security checks

For each request, authorization is the intersection of:
- tenant is active;
- module is released and compatible;
- tenant has the module entitlement (edition bundle or add-on);
- feature flag allows the requested rollout;
- actor has the required tenant-scoped RBAC permission;
- business policy and workflow approval permit the operation.

Cache only with bounded TTL and explicit invalidation on entitlement/role changes. Audit module enable/disable, plan changes, permission changes and administrative overrides. Fail closed if entitlement data is unavailable for a protected operation.

## 8. Release channels and compatibility

- `development`: developer builds; no customer data.
- `alpha`: internal feature testing; migrations may be reset.
- `beta`: selected tenants, explicit opt-in, telemetry and support contact.
- `stable`: supported production release with backup/restore evidence and upgrade notes.
- `LTS`: designated stable line with security/critical fixes and published support window.

A stable release requires green CI on the exact release commit, PostgreSQL migration tests, API compatibility tests, security/dependency scans, backup/restore rehearsal, signed artifacts, release notes and rollback instructions. No channel may promote a module whose status is planned.

## 9. Implementation roadmap

1. [x] Define edition, module, add-on and versioning policy.
2. [x] Add typed module catalog with module versions, dependencies and lifecycle statuses.
3. [x] Add deterministic edition/add-on resolver and catalog validation tests.
4. [ ] Persist tenant subscriptions, module entitlements and entitlement audit events.
5. [ ] Add server-side entitlement dependency to protected API routes and background jobs.
6. [ ] Add module administration UI and safe enable/disable workflow.
7. [ ] Add module compatibility manifests and independent migration ownership.
8. [ ] Add release channels, upgrade planner, signed manifests and client/API compatibility checks.
9. [ ] Add commercial usage metering, billing and contract/SLA integration only after product/legal policy is defined.

## 10. Acceptance criteria

- Invalid, duplicate, cyclic or missing module dependencies fail validation.
- An edition resolves only known modules; add-ons accept only modules marked as add-ons.
- Planned modules are never reported as activatable.
- Dependency resolution does not imply a hidden entitlement grant.
- API tests prove tenant A cannot use tenant B's module entitlement.
- Disabling a module blocks new operations without deleting historical records.
- A product upgrade can be rehearsed and restored from backup on PostgreSQL.
- Product, module, API, schema, AI model and client versions are independently visible in diagnostics.
