# AI Smart Retail — Reporting & Business Intelligence Specification

Status: approved implementation specification. Metrics must be computed from persisted, tenant-scoped operational records; mock/demo figures must never appear as live business data.

## Product principles
- One reporting center with role-aware views for owner, branch manager, cashier, inventory manager and accountant.
- Every report supports date range, branch, register, cashier, product/category and payment-method filters where applicable.
- Every KPI exposes its definition, source records, currency, timezone, calculation timestamp and drill-down route.
- Operational writes must not wait for heavy analytics. Use indexed queries first, then asynchronous rollups/materialized views as volume grows.
- Financial totals are derived from posted ledger entries, not mutable dashboard counters. Inventory valuation uses the configured costing policy.
- Never mix currencies in a total without an explicit conversion rate, source, timestamp and reporting currency.
- AI findings are advisory, evidence-linked and confidence-scored. No automatic refunds, price changes, write-offs or purchases.

## Reporting surfaces
1. Owner overview: gross/net sales, gross margin, posted expenses, operating result (only when all required cost/expense inputs exist), order count, average basket, payment mix, cash position, receivables/payables, stock value and alerts.
2. POS/cashier: sales by register, cashier and shift; tender mix; discounts; voids; returns; cash-in/out; expected-vs-counted closing variance.
3. Product/category: units, net sales, gross profit, margin, average selling price, discount rate, return rate, sell-through and top/bottom products.
4. Inventory: on-hand, reserved, available, stock value, aging, days of cover, stockout duration, slow/dead stock, shrinkage and reorder suggestions.
5. Finance: posted revenue/expense, gross profit, operating expenses, cash flow, receivables, payables, bank/cash balances, settlement reconciliation and period comparison.
6. People: cashier throughput, sales per labor hour (only with valid shift hours), void/discount/return rates and commission preview.
7. Branch comparison: normalized KPIs, same-period comparisons, branch contribution and transfer discrepancies.
8. Audit/risk: unusual void/refund/discount patterns, cash variances, negative-stock attempts, permission overrides and data-sync conflicts.
9. AI forecast: daily/weekly demand forecast with prediction interval, seasonality and data sufficiency; recommended reorder quantities with explainable drivers.

## Metric dictionary and definitions
- Gross sales: sum of posted sale line amounts before discounts and returns, excluding cancelled/unposted sales.
- Discounts: posted line/order discounts, reported separately.
- Net sales: gross sales minus discounts minus posted sales returns; tax treatment is displayed separately and configurable by jurisdiction.
- COGS: cost assigned to units sold/returned under the store's configured costing policy.
- Gross profit: net sales excluding collected tax minus COGS, with consistent tax treatment.
- Gross margin: gross profit / net sales excluding tax; null (not zero) when denominator is zero.
- Average basket: net sales / completed non-void sale count.
- Return rate: returned quantity / sold quantity for the same cohort or period; label the selected method.
- Stock on hand: sum of posted inventory movements; available = on hand - reservations.
- Cash variance: counted closing cash minus expected closing cash; never silently adjusted.
- Operating result: gross profit minus posted operating expenses; label incomplete if payroll/other required expense classes are not integrated.
- Forecast accuracy: compare forecast to actual using a named metric (e.g. WAPE); suppress scores when sample size is insufficient.

## API contract (versioned)
- GET /api/v1/reports/overview
- GET /api/v1/reports/sales
- GET /api/v1/reports/products
- GET /api/v1/reports/inventory
- GET /api/v1/reports/finance
- GET /api/v1/reports/cashiers
- GET /api/v1/reports/branches
- GET /api/v1/reports/alerts
- GET /api/v1/reports/export?format=csv|xlsx|pdf (permission-gated, asynchronous for large exports)
- GET /api/v1/reports/definitions (metric definitions and data freshness)

Common query parameters: from, to, branch_id, register_id, cashier_id, category_id, product_id, payment_method, currency. Enforce tenant and branch authorization server-side; ignore client-supplied tenant identifiers.

## UX requirements
- Global period selector: today, yesterday, 7 days, 30 days, month-to-date, previous month, custom.
- Compare to previous equivalent period; show absolute and percentage change, and avoid misleading percentages when baseline is zero.
- Drill down from every chart/KPI to authorized source rows.
- Persian/Arabic RTL and localized numbers/dates/currency; English/Turkish translations.
- Accessible tables accompany charts; filters persist per user; export includes filters and generated-at metadata.
- Clearly distinguish live, delayed, stale and incomplete data.

## Alert rules
- Reorder threshold reached; projected stockout before supplier lead time.
- Unusual refund/void/discount/cash variance compared with peer baseline and own history.
- Sudden sales/margin drop after accounting for day-of-week/seasonality.
- Payment settlement mismatch; overdue receivable/payable.
- Sync backlog, rejected events or stale branch data.

## Security, integrity and performance
- Role/permission gates per report and per branch.
- Every export and sensitive drill-down is audited.
- Parameterized queries, bounded date ranges, pagination and query timeouts.
- Never expose customer secrets or full payment-card data in reports.
- Avoid N+1 queries; add indexes for tenant_id, branch_id, posted_at, status and common joins.
- Cached aggregates are invalidated/versioned by source ledger watermark; stale cache is labelled.
- Retention and deletion follow legal policy; immutable ledger/audit data are not rewritten by report jobs.

## Release gates
- Metric unit tests include discounts, returns, tax, zero denominators, timezones and mixed currencies.
- Tenant/branch isolation tests cover every endpoint and export.
- Reconciliation tests prove dashboard totals match source ledgers.
- Load tests cover common date ranges and large exports.
- AI outputs include provenance, confidence and a human approval boundary.
