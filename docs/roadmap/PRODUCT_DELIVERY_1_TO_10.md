# Product Delivery Roadmap (Stages 1-10)

This roadmap is an execution ledger. A stage is not complete because it is described here; it is complete only when its code, migration, regression tests, CI evidence, and operational evidence exist on the same commit.

## 1. Stabilize the foundation

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
- [ ] Balance sheet and profit/loss reports.
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
- [ ] POS workflows and cash drawer reconciliation.
- [ ] CRM, customer support, and loyalty.

Exit gate: end-to-end purchase-to-stock and order-to-cash workflows with reconciliation tests.

## 5. Workflow and notifications

Status: **Transactional outbox core implemented; dispatch and workflow features remain**

- [x] Durable tenant-scoped outbox table with idempotent event deduplication.
- [x] Inventory movement events are enqueued in the same database transaction as stock posting.
- [x] Atomic SQLite claims and PostgreSQL skip-locked worker leasing, stale-lease protection, retry scheduling and dead-letter state with service tests.
- [ ] Background worker process and handler registry.
- [ ] Configurable multi-step approvals and separation of duties.
- [ ] In-app notifications and email provider adapter.
- [ ] Provider delivery adapters, idempotent event consumers, retry telemetry and operational dashboards.
- [ ] Complete actor/action history for workflow transitions.

Exit gate: retry/replay tests and no lost events across transaction failures.

## 6. AI and analytics

Status: **Not started**

- [ ] Tenant-scoped analytics data contracts and consent controls.
- [ ] Forecasting and anomaly detection with measurable baselines.
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

Exit gate: provider sandbox evidence, contract tests, idempotency, and operational runbooks.

## 8. User experience and clients

Status: **Not started**

- [ ] Persian/English interface with RTL/LTR support.
- [ ] Role-aware dashboards and accessible forms.
- [ ] Responsive mobile web/PWA.
- [ ] Offline queue and conflict-resolution UX.
- [ ] Desktop/mobile packaging only after API contracts stabilize.

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
