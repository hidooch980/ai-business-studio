# AI Business Studio — Master ERP Blueprint

Status: **Architecture baseline / planned scope**  
Implementation status: This document defines target architecture and acceptance criteria. It is not evidence that the listed modules are implemented or production-ready.

## 1. Product direction

Build a modular, multi-tenant, multi-company ERP with a shared operational and financial core. Each domain owns its data and invariants; cross-domain changes are coordinated through explicit application services, database transactions, and the transactional outbox. Avoid a distributed-monolith design and avoid premature microservices.

Primary outcomes:
- One source of truth for products, parties, stock, money, employees, documents, and approvals.
- Traceable procure-to-pay, order-to-cash, inventory, payroll, production, service, and project lifecycles.
- Accurate double-entry accounting with reconciliation and period controls.
- AI-assisted forecasting and anomaly detection with tenant isolation and human approval for consequential actions.
- Deployable as a modular monolith first, with stable API/event boundaries for later extraction if scale justifies it.

## 2. Shared platform foundation

### 2.1 Organization and tenancy
- Tenant → legal entity/company → branch/site → department/cost center hierarchy.
- Tenant-scoped records and composite tenant foreign keys for every cross-domain reference.
- Explicit company, branch, warehouse, register, and cost-center context on operational transactions.
- Per-company base currency, fiscal calendar, timezone, locale, tax profile, and numbering sequences.
- Consolidated reporting must preserve legal-entity boundaries and elimination entries.

### 2.2 Identity, access, and governance
- RBAC plus resource/attribute scope: tenant, company, branch, warehouse, register, department, and amount thresholds.
- Separation of duties: requester ≠ approver ≠ payer/poster for configured sensitive workflows.
- MFA, recovery, device/session management, scoped API keys, rate limits, and audit exports.
- Append-only audit trail with actor, action, object, timestamp, correlation ID, reason, and before/after hashes where appropriate.
- Privileged access expiry and emergency access review.
- No destructive deletion of posted financial or stock records; use reversals/compensating entries.

### 2.3 Shared master data
- Party registry for customers, suppliers, employees, carriers, service partners, and related contacts, with typed roles rather than duplicate identities.
- Product and service catalog; categories, attributes, variants, units, conversion factors, barcodes, bundles, kits, and substitute items.
- Addresses, contacts, tax identifiers, payment terms, currencies, exchange rates, price lists, and document numbering.
- Data-quality rules, duplicate detection, merge workflow, ownership, and import validation.

### 2.4 Documents and workflow
- Versioned document vault for contracts, invoices, receipts, payroll statements, delivery proofs, and attachments.
- Configurable workflow engine: draft → submitted → approved/rejected → posted/paid/fulfilled/closed.
- Multi-step approvals by amount, risk, entity, department, and transaction type.
- Delegation with expiry, escalation, SLA timers, reminders, and immutable approval history.
- Idempotent commands, optimistic concurrency, correlation IDs, and transactional outbox for cross-module events.

## 3. Business domain modules

### 3.1 Procurement and supplier management
- Supplier onboarding, due diligence, contacts, tax data, payment terms, and risk classification.
- Purchase requests, RFQs, bid comparison, purchase orders, revisions, approvals, and commitments.
- Partial receipts, quality inspection, rejected/returned goods, landed costs, and supplier invoices.
- Three-way match: purchase order ↔ goods receipt ↔ supplier invoice; tolerance and exception queues.
- Supplier balances, debit/credit notes, payment runs, performance scorecards, and contract renewals.
- **Demand-driven smart procurement:** forecast sales by SKU/branch, calculate inventory position and safety stock, detect fast movers and stockout risk, suggest reorder quantities and timing, compare supplier landed cost/reliability, and prepare approval-gated draft purchase requests. See [SMART_PROCUREMENT.md](SMART_PROCUREMENT.md). This is approved target scope, not implemented functionality.

### 3.2 Inventory and warehouse execution
- Multiple companies, sites, warehouses, zones, bins, and stock ownership/status.
- Units of measure and decimal precision; controlled conversion with base-unit normalization.
- Lot/batch, serial, expiry, warranty, quality status, country of origin, and traceability.
- Receipts, put-away, picks, packing, dispatch, transfers, reservations, replenishment, cycle counts, and full stocktakes.
- FEFO/FIFO/weighted-average valuation policies, landed-cost allocation, write-offs, and stock ageing.
- Negative-stock prevention, concurrency-safe balances, immutable movement ledger, and reconciliation against GL.
- Quarantine, damaged/expired/recall stock, consignment, subcontractor stock, and stock in transit.

### 3.3 Sales, CRM, and customer experience
- Leads, opportunities, pipeline, activities, quotations, contracts, orders, delivery, invoices, and returns.
- Customer segmentation, consent/preferences, interaction history, credit limits, payment terms, and collections.
- Price lists, promotions, coupons, bundles, loyalty, gift cards, commissions, and controlled discounts.
- Smart POS with barcode/QR, multi-tender, cash/card/hosted payments, suspended sales, receipts, shifts, offline drafts, and reconciliation.
- Customer portal, order tracking, self-service invoices, support requests, and satisfaction feedback.

### 3.4 Finance and accounting
- Configurable chart of accounts, account normal-balance rules, dimensions, cost centers, projects, and intercompany accounts.
- General ledger, AP, AR, cash/bank, journals, accruals, prepayments, fixed assets, depreciation, and lease schedules.
- Automated posting profiles for sales, purchases, inventory, payroll, production, projects, tax, and payments.
- Bank statement import, matching rules, reconciliation queues, payment batches, checks, and cash forecasts.
- Multi-currency revaluation, realized/unrealized FX, rounding policy, and source/time-stamped rates.
- Tax engine by jurisdiction/effective date, withholding, VAT/sales tax, exemptions, and audit exports.
- Period close checklist, controlled reopening, lock dates, consolidation, eliminations, trial balance, P&L, balance sheet, cash flow, and audit trail.
- Posted journals and closed-period data are immutable; corrections use linked reversals and adjustment journals.

### 3.5 Cash management and treasury
- Multiple cash registers, tills, petty cash funds, opening floats, cash-in/out, shift handover, counted close, and variance approval.
- Bank accounts, transfers, payment instructions, reconciliation, liquidity forecast, and cash pooling (where applicable).
- Payment lifecycle with idempotency, provider references, signed webhook verification, timeout inquiry, refunds, chargebacks, and suspense/reconciliation state.
- Never treat a network timeout as payment failure; never retry a non-idempotent charge without provider reconciliation.
- Do not store card PAN, CVV, PIN, track data, or sensitive authentication data.

### 3.6 Human resources and payroll
- Employee master, legal entity, department, job, grade, contract, compensation history, documents, and lifecycle.
- Attendance, shifts, leave, overtime, travel, timesheets, approvals, and payroll cut-off.
- Configurable gross-to-net rules by country, jurisdiction, effective date, employee type, and contract.
- Earnings, allowances, deductions, benefits, advances, loans, garnishments, tax, insurance, employer costs, and final settlement.
- Payroll preview, variance checks, approval, payslips, payment file, bank reconciliation, and accounting journal.
- Strict segregation: payroll preparer, approver, and payment releaser; encrypt highly sensitive employee data and restrict exports.
- Never hard-code tax/insurance rates; maintain versioned rule packs with effective dates and test fixtures.

### 3.7 Manufacturing and planning
- Bills of material, routings, work centers, capacity, production orders, material requirements, and scheduling.
- Material issue/return, work-in-progress, labor/overhead allocation, scrap/by-products, yield, and variance.
- Quality gates, lot genealogy, batch traceability, and recall simulation.
- MRP forecasts must distinguish firm orders, forecasts, safety stock, lead times, and supplier constraints.

### 3.8 Quality, maintenance, and assets
- Incoming/in-process/final inspection plans, nonconformance, corrective/preventive actions, and supplier quality.
- Fixed asset register, capitalization, componentization, depreciation books, disposals, transfers, and impairment.
- Equipment registry, preventive maintenance plans, work orders, spare parts, downtime, and maintenance cost.
- Calibration, warranty, safety checks, and service history.

### 3.9 Projects, services, and field operations
- Project budgets, milestones, tasks, resources, timesheets, expenses, commitments, and earned-value metrics.
- Service desk, ticket SLAs, warranty/RMA, repair estimates, parts consumption, technician scheduling, and customer sign-off.
- Fleet, route planning, shipment tracking, proof of delivery, freight rating, and carrier settlement.

### 3.10 Legal, compliance, and administration
- Contract lifecycle, obligations, renewals, approvals, retention, and searchable metadata.
- Policy acknowledgements, incident register, privacy requests, retention schedules, and data export/deletion controls subject to accounting/legal retention.
- Regulatory reporting packs and jurisdiction-specific localization as independently versioned modules.

## 4. Cross-module transaction invariants

- Sales order → reserve stock → fulfill shipment → invoice → payment allocation → revenue/COGS posting → customer balance.
- Purchase order → receipt/inspection → inventory valuation → supplier invoice match → AP posting → payment → bank reconciliation.
- Payroll run → approved gross-to-net calculation → payroll liability journal → payment batch → bank reconciliation.
- Inventory movement and corresponding valuation/GL event must be atomic or recoverably linked through a durable outbox.
- Every external side effect has a stable idempotency key and a reconciliation path.
- No module may update another module's tables directly; use domain services and explicit event contracts.
- Every posted event carries tenant, company, actor/system identity, source document, currency, effective date, and correlation ID.

## 5. Product editions and modular versioning\n\nThe edition, module dependency, entitlement, lifecycle and release-versioning contract is defined in [PRODUCT_EDITION_AND_MODULE_VERSIONING.md](PRODUCT_EDITION_AND_MODULE_VERSIONING.md). This document is the product packaging baseline; its edition bundles are targets and do not imply that planned modules are implemented.\n\n## 6. AI and decision intelligence

### 6.1 Intelligence services
- Forecasting: demand, replenishment, cash flow, collections, workforce capacity, production, and service load.
- Detection: unusual discounts, duplicate invoices, stock shrinkage, suspicious refunds, payroll anomalies, supplier price drift, and journal outliers.
- Optimization: reorder quantities, replenishment routes, production schedules, staffing suggestions, and cash allocation.
- Natural-language assistant over permission-filtered business facts with source citations, data freshness, and explicit uncertainty.
- Explainable recommendations: inputs, assumptions, confidence, expected impact, alternatives, and reason codes.

### 6.2 AI safety and governance
- Tenant-isolated feature stores and retrieval; no cross-tenant leakage.
- Explicit consent and policy for model training; customer data is not used for training by default.
- PII minimization, redaction, retention limits, access logs, and export controls.
- Evaluation datasets, baseline comparisons, drift monitoring, model/version registry, rollback, and human feedback.
- AI is advisory by default. Financial posting, payments, payroll changes, credit decisions, refunds, and stock adjustments require policy checks and authorized human confirmation.
- Never let model output bypass RBAC, approval workflows, accounting invariants, or idempotency.

## 6. Analytics and management intelligence
- Operational dashboards by role, company, branch, warehouse, register, department, and period.
- Financial statements, working capital, cash conversion cycle, gross margin, inventory turns, ageing, fill rate, supplier lead time, and payroll-to-revenue.
- Drill-through from KPI to source transaction with the same permission checks.
- Metric definitions, lineage, freshness, reconciliation status, and saved report versions.
- Export controls, scheduled reports, alert thresholds, and anomaly queues.

## 7. Integration and platform engineering
- Versioned REST API, webhook subscriptions, import/export jobs, and documented event schemas.
- Provider adapters for payment, banking, e-invoice/tax, email/SMS, identity, shipping, and attendance devices.
- Secrets manager, rotation, signed webhook validation, replay defense, provider circuit breakers, retries, and dead-letter operations.
- Modular monolith initially; bounded contexts and outbox contracts allow later service extraction.
- PostgreSQL as production source of truth; SQLite remains for local/test workflows only where supported.
- Migration rehearsal, backups, point-in-time recovery, restore drills, structured logs, metrics, traces, health/readiness, SLOs, and incident runbooks.
- Accessibility, Persian RTL/English LTR, localization, timezone-safe dates, and currency/number formatting.

## 8. Data architecture and controls
- Use integer minor units for money and explicit currency codes; never binary floating point for posted amounts.
- Use decimal quantities with explicit unit precision; preserve normalized base quantities and conversion version.
- Store UTC instants plus business timezone/effective date where business meaning requires it.
- Every business document has a lifecycle state, version, actor, timestamps, and source references.
- Use soft deactivation for master data; never erase referenced history.
- Enforce tenant-safe composite foreign keys, database constraints, indexes, and concurrency controls.
- Define retention and archival by data class; protect payroll, identity, financial, and customer personal data.
- Reconciliation jobs compare operational subledgers with GL and produce actionable exceptions, never silent auto-corrections.

## 9. Delivery sequence and gates

### Phase A — Core platform hardening
- Complete MFA/recovery, scoped permissions, approval engine, audit search/export, master-party model, company/branch/cost-center dimensions, document vault, localization foundation.
- Gate: tenant isolation, privilege escalation, audit integrity, recovery, migration upgrade and restore tests.

### Phase B — Inventory and procure-to-pay
- Units/conversions, categories, lots/serial/expiry, locations/bins, reservations, transfers, valuation, purchase orders, receipts, supplier invoices, three-way match.
- Add demand-driven replenishment in stages: deterministic inventory position/reorder/safety-stock first; then forecast-based fast-mover and stockout prioritization; supplier comparison and branch transfers; finally approval-gated scheduled draft requests.
- Gate: concurrency, traceability, valuation-to-GL reconciliation, duplicate/replay and partial receipt tests; demand forecast backtesting and stale-data safeguards.

### Phase C — Sales, POS, and order-to-cash
- Customer/CRM, quotes/orders, POS cash-first vertical slice, register shifts, payment adapter contracts, split tender, refunds, returns, offline draft synchronization.
- Gate: sale-to-stock-to-GL atomicity, payment provider sandbox/reconciliation, cash variance, refund and offline replay tests.

### Phase D — Finance and treasury
- Account policy, AP/AR, bank/cash, reconciliation, FX, tax rule packs, period close/reopen, fixed assets, cash forecasting.
- Gate: trial balance, subledger-to-GL, FX rounding, tax effective-date, period lock and audit tests.

### Phase E — HR and payroll
- Employee lifecycle, attendance/leave, configurable payroll rules, payslips, approvals, payments, accounting posting.
- Gate: jurisdiction rule validation, payroll privacy, role separation, gross-to-net fixtures, payment and journal reconciliation.

### Phase F — Manufacturing, quality, assets, projects, service, logistics
- Build only after stock/finance/master data foundations are stable.
- Gate: material genealogy, WIP/variance, asset depreciation, project cost reconciliation, SLA and delivery proof tests.

### Phase G — AI and analytics
- Governed data marts, KPI lineage, forecasts, anomaly detection, assistant with citations, model evaluation and monitoring.
- Gate: tenant authorization, privacy, baseline improvement, drift alert, rollback, and approval bypass tests.

### Phase H — Production readiness
- Staging, load/security testing, disaster recovery, restore rehearsal, operational dashboards, incident drills, user acceptance, signed release artifacts.
- Gate: all critical/high issues resolved, all prior gates passed on one commit, and explicit release approval.

## 10. Non-goals and safeguards
- No real payment processing before provider selection, credentials, sandbox contract tests, and reconciliation runbooks.
- No live payroll/tax calculation until jurisdiction and effective-date rule packs are selected and validated by a qualified local professional.
- No automatic financial actions based solely on an AI prediction.
- No production readiness claim based only on unit tests or green foundation CI.
- No merge or release without explicit approval.

## 11. Definition of done for every module
A module is complete only when it has:
1. Domain model and migration with tenant-safe constraints.
2. Service layer enforcing state transitions and business invariants.
3. Authorized API and user-facing workflow.
4. Audit events and idempotency for retryable commands.
5. Unit, integration, negative-authorization, concurrency, and migration tests.
6. Operational logs, metrics, recovery/reconciliation procedure, and documentation.
7. CI evidence on the exact commit and staging acceptance before production use.
