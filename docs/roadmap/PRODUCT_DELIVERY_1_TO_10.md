# Product Delivery Roadmap (Stages 1-10)

This roadmap is an execution ledger. A stage is not complete because it is described here; it is complete only when its code, migration, regression tests, CI evidence, and operational evidence exist on the same commit.

## 0. Product editions and modular versioning\n\nStatus: **Policy and initial catalog implemented; tenant entitlement enforcement remains**\n\n- [x] Define Starter, Growth, Business and Enterprise packaging targets with independently licensable add-ons.\n- [x] Add module catalog with stable IDs, independent SemVer, dependency graph and lifecycle states.\n- [x] Add edition/add-on resolution and validation tests; planned modules fail closed.\n- [ ] Persist tenant entitlements and enforce them on API routes, jobs and integrations.\n- [ ] Implement safe module enable/disable, compatibility checks and upgrade planner.\n- [ ] Add release channels, signed module manifests, usage metering and commercial billing policy.\n\nDetails: `docs/architecture/PRODUCT_EDITION_AND_MODULE_VERSIONING.md`. Catalog metadata is not runtime licensing or production activation.\n\nExit gate: tenant-isolated entitlement tests, safe enable/disable, migration/restore rehearsal and signed release evidence.\n\n## 1. Stabilize the foundation

Status: **In progress**

- [x] Python 3.11/3.12 CI matrix with PostgreSQL 16.
- [x] Ruff lint and pytest with warnings treated as errors.
- [x] SQLite foreign-key enforcement enabled by the application engine.
- [x] Production configuration rejects missing/non-PostgreSQL databases and insecure session cookies.
- [x] Dependency audit step added to CI.
- [x] Verified CI run at `e8b52090e822c35517f1ee973c30ef701581ea97`: Python 3.11 and 3.12, Ruff, 47 tests, pip-audit, Compose validation, and Docker build all passed.
- [x] Alembic metadata imports all catalog, identity, inventory, and outbox models so schema inspection sees the active domain metadata.
- [x] SQLite and PostgreSQL migration chains include accounting periods and indexed login-throttle retention cleanup; current migration head is `0013_login_rate_limit_retention`.
- [x] Verified CI run at `26b904b43bf1aa40ec7a5b865e5dca7da2833b2f`: Python 3.11/3.12, Ruff, tests, PostgreSQL 16 integration, dependency audit, Compose validation, shell/systemd checks, and Docker build all passed.
- [ ] Upgrade rehearsal with representative existing data from the previous supported schema.

Exit gate: all checks green on the same head SHA and both SQLite/PostgreSQL migration paths verified.

## 2. Security and tenant isolation

Status: **Foundation implemented; production security work remains**

- [x] Argon2 password hashing and opaque session tokens.
- [x] Session expiry/revocation and session-bound CSRF.
- [x] Persistent login throttling.
- [x] Tenant-scoped RBAC, invitation lifecycle, owner safeguards, and append-only audit triggers.
- [x] Cross-tenant authorization regression coverage.
- [ ] MFA and account recovery.
- [x] User-owned session listing and individual session revocation, including current-session revocation.
- [ ] Device metadata/fingerprinting and centralized administrator session controls.
- [x] Per-tenant invitation create/resend limit (20 actions per rolling hour), serialized on the tenant row.
- [x] Login throttling by account-only, account+IP, and independent IP keys to resist distributed brute force and password spraying; regression tests cover lockout, email normalization, and ensure successful login cannot reset the shared IP counter.
- [x] Expired login-throttle records are pruned after 30 days, with an indexed `updated_at` field and migration coverage.
- [ ] API-wide IP/account rate limiting and failed-invitation abuse controls.
- [x] PostgreSQL concurrency regression test proves simultaneous deactivation cannot remove the last two active owners.
- [ ] Additional PostgreSQL concurrency stress tests for role and invitation operations.
- [ ] Independent security review and threat-model sign-off.

Exit gate: negative authorization tests, race tests, MFA/recovery tests, and security review complete.

## 3. Accounting and finance

Status: **Journal foundation implemented; accounting domain incomplete**

- [x] Tenant-scoped double-entry journals using integer minor units.
- [x] Balanced totals and one-sided debit/credit constraints.
- [x] Idempotent creation and one-time compensating reversal.
- [x] Append-only mutation guards and overposting protection for SQLite/PostgreSQL.
- [x] Tenant-scoped chart-of-accounts catalog with typed accounts, same-type parent hierarchy, tenant-safe parent foreign keys and guarded deactivation.
- [x] Link journal lines to active tenant chart accounts with composite tenant foreign keys; serialize posting against concurrent account deactivation.
- [ ] Enforce account-type/normal-balance policy at posting time.
- [x] Tenant-scoped accounting periods with overlap prevention, immutable close state, audit events, and open-period posting enforcement.
- [ ] Authorized period reopening workflow (controlled adjustment only) and period-end closing checklist.
- [x] Tenant-scoped trial balance by currency and posting date, with debit/credit totals and unmapped-line detection.
- [x] Tenant-scoped general ledger with date range, currency filter, opening/closing balances, and running balances.
- [x] Tenant-scoped income statement and balance sheet reports with currency/date filters, normal-balance calculations, cumulative earnings, unmapped-line visibility, and reconciliation status.
- [x] Income statement and balance sheet reports with date/currency filters and unmapped-line reconciliation visibility (implemented above).
- [ ] Reconciliation and adjustment workflows.
- [ ] Multi-currency FX source, conversion, and rounding policy.
- [ ] Tax rules and audit-ready exports.

Exit gate: accounting invariants verified with accounting-domain fixtures and PostgreSQL integration tests.

## 4. ERP business modules

Status: **Product catalog and inventory ledger foundations implemented; ERP workflows remain**

- [x] Tenant-scoped product catalog with SKU/barcode uniqueness, search, update, soft-deactivation, permission checks and audit events.
- [x] Tenant-scoped warehouses and immutable receipt/issue/adjustment stock movements.
- [x] Prevent product and warehouse deactivation while stock remains; serialize deactivation against concurrent inventory movements with row locks and regression tests.
- [x] Idempotent movement creation, non-negative stock guard, database-maintained balance projection and tenant-composite foreign keys.
- [x] SQLite and PostgreSQL append-only movement triggers with integration coverage.
- [ ] Product/service categories, unit conversion and barcode/QR workflows.
- [ ] Batches, expiry, stock valuation and inventory reconciliation.
- [ ] Purchase orders, goods receipt, supplier bills, and supplier balances.
- [ ] Sales orders, invoices, returns, discounts, and customer balances.
- [ ] Smart POS: cashier workspace, barcode/QR lookup, customer display, receipts, discounts/tax, suspended sales and role-aware overrides.
- [ ] Cash/card-terminal/hosted-online payments, split tender, idempotent payment state machine, signed webhooks, refunds and reconciliation.
- [ ] Cashier/register shifts, opening float, cash in/out, handover, close/count/variance and supervisor controls.
- [ ] Sales fulfillment, stock reservation/release, returns, customer credit/loyalty, and atomic inventory/accounting/outbox posting.
- [ ] Offline draft queue with idempotent synchronization, conflict resolution, encrypted device storage and explicit provisional status.
- [ ] POS analytics, AI advisory insights, device adapters (scanner/printer/customer display/cash drawer), operational monitoring and release gates.
- [ ] Implemented Smart POS scope and staged release gates documented in `docs/architecture/SMART_POS.md`; documentation is scope approval, not implementation evidence.
- [ ] CRM, customer support, and loyalty.
- [ ] Smart procurement data readiness: supplier master, product categories, units/conversions, branch/warehouse stock and trusted sales/receipt history.
- [ ] Deterministic replenishment engine: sellable inventory position, reservations, inbound supply, safety stock, reorder point, days of cover, MOQ/pack rounding and draft purchase recommendations.
- [ ] Fast-mover and stockout-risk prioritization with demand acceleration, seasonality/promotion context, margin, expiry, storage and budget constraints.
- [ ] Supplier scorecards and RFQ comparison using landed cost, quality, lead-time variability, fill rate, reliability, payment terms and contract eligibility.
- [ ] Purchase request approval workflow, separation of requester/approver, draft-to-PO lineage, partial receipts and three-way invoice matching.
- [ ] Forecast backtesting, confidence intervals, drift monitoring, stale-data fail-safe, branch transfer optimization and scheduled draft recommendations.
- [ ] Smart procurement scope and acceptance criteria documented in `docs/architecture/SMART_PROCUREMENT.md`; documentation is not implementation evidence.

Exit gate: end-to-end purchase-to-stock and order-to-cash workflows with reconciliation tests; smart procurement additionally requires forecast backtesting, tenant/permission tests, approval controls, and staging evidence from recommendation through receipt and invoice match.

## 5. Workflow and notifications

Status: **Transactional outbox core implemented; dispatch and workflow features remain**

- [x] Durable tenant-scoped outbox table with idempotent event deduplication.
- [x] Inventory movement events are enqueued in the same database transaction as stock posting.
- [x] Atomic SQLite claims and PostgreSQL skip-locked worker leasing, stale-lease protection, retry scheduling and dead-letter state with service tests.
- [x] Reusable leased-batch dispatcher with typed handler registry, isolated per-event sessions, delivery acknowledgement, retry handling, and dead-letter handling; regression tests cover success, handler failure, and unknown event types.
- [x] Configurable handler-factory registry, long-running polling worker, bounded batch/poll settings, graceful SIGTERM/SIGINT shutdown, console entry point, and hardened systemd service template.
- [ ] Concrete inventory/provider handler package, worker health/metrics, and operational alerting.
- [ ] Configurable multi-step approvals and separation of duties.
- [ ] In-app notifications and email provider adapter.
- [ ] Provider delivery adapters, idempotent event consumers, retry telemetry and operational dashboards.
- [ ] Complete actor/action history for workflow transitions.

Exit gate: retry/replay tests and no lost events across transaction failures.

## 6. AI and analytics

Status: **Not started**

- [ ] Tenant-scoped analytics data contracts and consent controls.
- [ ] Forecasting and anomaly detection with measurable baselines.
- [ ] Demand forecasting by SKU/branch with stockout-censored demand, promotion/seasonality context, backtesting and confidence calibration.
- [ ] Replenishment recommendation explanations with forecast, inventory position, cover days, expected stockout, supplier lead time, estimated landed cost and expected impact.
- [ ] AI assistant with citations to tenant-authorized business data.
- [ ] Human approval for financial or operational actions.
- [ ] Model monitoring, drift detection, evaluation sets, and rollback.
- [ ] No training on customer data without explicit policy and consent.

Exit gate: offline evaluation, permission tests, model monitoring, and human-approval enforcement.

## 7. External integrations

Status: **Not started**

- [ ] Payment-provider sandbox adapters and verified webhook signatures.
- [ ] Email/SMS provider adapters.
- [ ] Import/export and documented public API.
- [ ] External ERP/accounting connectors with mapping and reconciliation.
- [ ] Secret rotation, webhook replay defense, and provider outage handling.
- [ ] Supplier catalog/price-list import and supplier EDI/API adapters with validation, provenance and replay protection.

Exit gate: provider sandbox evidence, contract tests, idempotency, and operational runbooks.

## 8. User experience and clients

Status: **Not started**

- [ ] Persian/English interface with RTL/LTR support.
- [ ] Role-aware dashboards and accessible forms.
- [ ] Responsive mobile web/PWA.
- [ ] Offline queue and conflict-resolution UX.
- [ ] Desktop/mobile packaging only after API contracts stabilize.
- [ ] Smart procurement workbench: buy-now/soon/watch queues, fast movers, stockout alerts, excess/expiry alerts, supplier comparison, scenario simulation and explainable recommendations.

Exit gate: accessibility, localization, browser/device, and offline recovery tests.

## 9. Deployment and operations

Status: **Container foundation implemented; operational controls remain**

- [x] Reproducible Dockerfile with non-root runtime and read-only app filesystem.
- [x] PostgreSQL Compose service with separate non-superuser app and migration roles.
- [x] CI validation of Compose configuration and container image build (verified on a green run; re-run for each later commit).
- [ ] Separate dev/staging/production deployment environments.
- [x] Separate non-superuser runtime/migration database roles and local-only app port binding.
- [ ] TLS termination and external secret manager.
- [ ] Structured logs, metrics, traces, health/readiness checks, and alerting.
- [x] Encrypted PostgreSQL backup and guarded restore scripts with checksum/permission checks and documented recovery steps.
- [ ] Scheduled off-host backup execution, monitoring/alerting, and verified restore rehearsal.
- [ ] Capacity/load tests, migration runbook, rollback and incident response.

Exit gate: staging deployment, restore rehearsal, load test, and incident drill signed off.

## 10. Release readiness

Status: **Blocked**

- [ ] All prior stage exit gates complete.
- [ ] No unresolved critical/high security findings.
- [ ] Dependency and secret scans clean.
- [ ] Fresh-install and upgrade tests pass.
- [ ] Release artifacts are reproducible and signed.
- [ ] User acceptance test and explicit release approval.
- [ ] Merge PR and publish release only after approval.

A green foundation CI run is not evidence that stages 2-10 are complete. The current branch is not production-ready and must not be used for real customer financial records.

## Master ERP architecture baseline

The comprehensive target architecture, domain boundaries, cross-module invariants, AI governance, integration requirements, phased delivery gates, and module definition-of-done are maintained in [MASTER_ERP_BLUEPRINT.md](../architecture/MASTER_ERP_BLUEPRINT.md).

Demand-driven procurement scope, calculation rules, controls, lifecycle, dashboards, and acceptance criteria are detailed in [SMART_PROCUREMENT.md](../architecture/SMART_PROCUREMENT.md).

These blueprints are approved scope only. The checkboxes and stage statuses above remain the execution ledger; do not mark any capability complete until its implementation, migrations, tests, CI evidence, and operational acceptance exist on the same commit.


## 0.1 Tenant subscription and module activation
Status: **Implemented in feature branch; awaiting CI/review**

- [x] Persist one subscription per tenant and per-module entitlements.
- [x] Provision Starter on new tenant registration and backfill existing tenants.
- [x] Add tenant-scoped module list, edition change and module enable/disable endpoints.
- [x] Enforce RBAC, CSRF, subscription status, module lifecycle and transitive dependencies.
- [x] Preserve historical data on edition downgrade/module disable.
- [x] Apply module enforcement to the smart procurement preview endpoint.
- [ ] Apply entitlement checks to every future API route, background worker and integration.
- [ ] Implement paid add-on checkout, payment verification, renewal, expiry and proration.
- [ ] Add admin UI for subscription and module management.

Details: `docs/architecture/TENANT_MODULE_MANAGEMENT.md`.
