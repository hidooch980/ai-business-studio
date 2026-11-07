# Reporting implementation backlog

## Phase R1 — trusted reporting foundation
- Define canonical posted-sale, return, payment, inventory-movement, expense and shift facts.
- Add metric definitions and typed response schemas.
- Implement overview and sales reports from authoritative records.
- Add tenant/branch permission checks and bounded filters.
- Add reconciliation tests comparing aggregates to source rows.
- Provide CSV export with formula-injection protection and audit metadata.

## Phase R2 — inventory and finance
- Inventory aging, available stock, stock valuation and days-of-cover.
- Finance ledger summaries, cash flow, receivables/payables and settlement matching.
- Costing policy configuration and effective-dated cost history.
- Branch comparison and cashier/shift reports.

## Phase R3 — analytics and alerting
- Scheduled report delivery, saved report definitions and alert rules.
- Background export jobs and materialized aggregate tables.
- AI forecasting, anomaly detection and explainable recommendations.
- Data-quality and sync-freshness monitoring.

## Non-negotiable rules
- Do not create fake metrics from sample data in production.
- Do not call sales less tax "profit"; profit requires COGS and a defined tax basis.
- Do not infer payroll cost from sales commissions unless posted/approved.
- Do not compare currencies without explicit FX conversion metadata.
- AI recommendations cannot execute financial or stock mutations without human authorization.
