# Product Delivery Roadmap (Stages 1-10)

This roadmap is an execution ledger. A stage is not complete because it is described here; it is complete only when its code, migration, regression tests, CI evidence, and operational evidence exist on the same commit.

## 1. Stabilize the foundation

Status: **In progress**

- [x] Python 3.11/3.12 CI matrix with PostgreSQL 16.
- [x] Ruff lint and pytest with warnings treated as errors.
- [x] SQLite foreign-key enforcement enabled by the application engine.
- [x] Production configuration rejects missing/non-PostgreSQL databases and insecure session cookies.
- [x] Dependency audit step added to CI.
- [x] Verified CI run at `b97beb3e79fbf357652c84777628441da447d405`: Python 3.11 and 3.12, Ruff, 38 tests, pip-audit, Compose validation, and Docker build all passed.
- [ ] Upgrade rehearsal with representative existing data.
- [ ] Rehearse upgrade from the previous supported schema with representative data.

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
- [ ] Chart of accounts and account-type validation.
- [ ] Accounting periods, period close/reopen authorization, and locked periods.
- [ ] Trial balance, general ledger, balance sheet, and profit/loss reports.
- [ ] Reconciliation and adjustment workflows.
- [ ] Multi-currency FX source, conversion, and rounding policy.
- [ ] Tax rules and audit-ready exports.

Exit gate: accounting invariants verified with accounting-domain fixtures and PostgreSQL integration tests.

## 4. ERP business modules

Status: **Product catalog and inventory ledger foundations implemented; ERP workflows remain**

- [x] Tenant-scoped product catalog with SKU/barcode uniqueness, search, update, soft-deactivation, permission checks and audit events.
- [x] Tenant-scoped warehouses and immutable receipt/issue/adjustment stock movements.
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

Status: **Not started**

- [ ] Durable background job/outbox pattern.
- [ ] Configurable multi-step approvals and separation of duties.
- [ ] In-app notifications and email provider adapter.
- [ ] Retry, dead-letter, deduplication, and idempotent event consumers.
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
- [ ] TLS, secret manager, least-privilege database roles.
- [ ] Structured logs, metrics, traces, health/readiness checks, and alerting.
- [ ] Automated encrypted backups and tested restore rehearsal.
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
