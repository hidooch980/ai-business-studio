# Smart Procurement & Demand-Driven Replenishment

Status: **Approved target scope / partially implemented preview; not production-ready**

## 1. Objective

Generate explainable purchase recommendations from actual demand, sales velocity, stock position, committed supply, supplier lead time, service level, shelf life, cash constraints, and purchasing policy. The system must prevent avoidable stockouts without creating excess or dead stock.

This module is decision support first. It may prepare draft purchase requests automatically, but it must not issue purchase orders, commit funds, or pay suppliers without the configured human approval workflow.

## 2. Inputs and source-of-truth rules

- Sales history by SKU, branch, channel, day/week, promotion, and season; distinguish fulfilled sales from cancelled orders, returns, and stockout-censored demand.
- Current on-hand stock by warehouse/bin/status, including sellable, reserved, quarantined, damaged, expired, and in-transit quantities.
- Open purchase orders, confirmed supplier quantities, expected receipt dates, transfer orders, backorders, and customer reservations.
- Supplier lead-time history (median and variability), minimum order quantity, order multiples, pack size, price breaks, capacity, reliability, payment terms, and contract constraints.
- Product shelf life, expiry/lot rules, substitutes, criticality, margin, carrying cost, and storage capacity.
- Cash budget, approved purchasing limits, tax/landed-cost assumptions, and branch/warehouse replenishment policy.

All inputs must be tenant- and company-scoped, timestamped, traceable to source records, and checked for freshness and quality. Missing or stale inputs lower confidence and must be visible.

## 3. Demand and replenishment calculation

For each SKU × warehouse, calculate:

- Forecast demand over the replenishment lead time plus review period.
- Safety stock from demand variability, lead-time variability, and the configured target service level.
- Inventory position = sellable on-hand + confirmed inbound supply - reservations - backorders (with explicit treatment of transfers and blocked stock).
- Reorder point = expected lead-time demand + safety stock.
- Suggested buy quantity = target stock position - inventory position, rounded to supplier pack/order multiples and constrained by MOQ, shelf life, capacity, and budget.

The forecast must compare suitable baselines (e.g. seasonal naive, moving average, exponential smoothing) with more advanced models only when enough clean history exists. Record forecast horizon, model/version, confidence interval, training window, and error metrics. New products use controlled analog/category estimates and lower confidence rather than fabricated precision.

## 4. High-sales and urgency prioritization

Prioritize products using a transparent score combining:
- Recent sales velocity and acceleration (with promotion/seasonality context).
- Forecast stockout date and expected lost-sales risk.
- Gross-margin contribution and customer/order criticality.
- Supplier lead time and delivery reliability.
- Current stock cover, expiry risk, and excess/slow-moving inventory.
- Cash required and budget availability.

High sales alone must not trigger unlimited buying. Apply caps, shelf-life limits, margin checks, demand-shock detection, and approval thresholds. Separate true demand growth from one-off bulk orders, promotions, returns, and data anomalies.

## 5. Recommendation lifecycle

1. Detect need and create a versioned recommendation.
2. Explain why: sales trend, forecast, available stock, inbound orders, cover days, expected stockout date, target service level, supplier lead time, suggested quantity, estimated cost, and confidence.
3. Simulate alternatives: buy now, buy later, split order, transfer between branches, substitute product, or do not buy.
4. Validate supplier, MOQ, pack size, contract price, budget, warehouse capacity, expiry, and duplicate open orders.
5. Create a draft purchase request; never silently create an approved purchase order.
6. Route through amount/risk/category-based approvals with requester/approver separation.
7. Convert approved request to RFQ/PO; retain recommendation-to-order lineage.
8. Reconcile partial receipts, quality rejection, invoice three-way match, supplier performance, and forecast error.

## 6. Supplier selection

Rank eligible suppliers using landed unit cost (not unit price alone), quality/rejection rate, on-time delivery, lead-time variability, fill rate, payment terms, capacity, contract status, and risk. Show score components and allow policy-based exclusions. Do not select an unapproved supplier or violate contract/quality restrictions merely because its price is lower.

## 7. Multi-branch optimization

Before buying externally, identify safe inter-branch transfer opportunities after accounting for each source branch's own forecast, safety stock, reservations, transfer time/cost, and stock ownership. Never treat a transfer as free or instantly available. Provide a network-level view while preserving legal-entity and warehouse permissions.

## 8. Controls and exception handling

- Duplicate recommendation/PO detection and idempotent generation.
- No negative stock, no double counting inbound supply, and no counting quarantined/expired stock as sellable.
- Human approval for purchase commitments, supplier changes, budget overrides, and exceptional quantities.
- Hard limits for shelf life, storage, budget, supplier exposure, and price variance.
- Pause recommendations when source data is stale, inventory reconciliation is unresolved, or forecast drift/anomaly thresholds are breached.
- Record overrides with actor, reason, before/after values, and audit event.
- AI cannot bypass RBAC, segregation of duties, approval policies, or accounting/inventory invariants.

## 9. Dashboards and alerts

- Items to buy now / soon / monitor.
- Fast movers, accelerating demand, stockout risk, lost-sales estimate, and days of cover.
- Overstock, dead stock, expiry exposure, and excess cash tied in inventory.
- Supplier scorecards, price drift, lead-time reliability, open order delays, and fill rate.
- Recommended quantity, estimated landed cost, budget impact, confidence, and expected service-level impact.
- Forecast accuracy and bias by SKU/category/branch, with drill-through to source transactions.

## 10. Acceptance criteria

A production-ready implementation must include:
1. Tenant-safe schema and migrations for policies, forecast snapshots, recommendations, supplier metrics, and decision history.
2. Deterministic inventory-position and reorder calculations with unit/pack conversion tests.
3. Historical backtesting against simple baselines, including stockout-censored demand and promotion/seasonality cases.
4. Tests for partial receipts, duplicate open POs, returns, transfers, quarantined/expired stock, concurrent changes, stale data, MOQ, budget, and shelf life.
5. Permission tests, approval separation, immutable audit history, idempotency, and replay protection.
6. Forecast quality monitoring, confidence calibration, drift alerts, and safe fallback to rule-based calculations.
7. End-to-end staging evidence from recommendation → approval → PO → receipt → invoice match → inventory/GL reconciliation.
8. No automatic supplier payment or unapproved PO issuance.

## 11. Delivery sequence

- **SP-1 Data readiness:** product categories, UOM conversions, branch/warehouse stock, supplier master, purchase order/receipt data, event timestamps, and data-quality checks.
- **SP-2 Deterministic replenishment:** inventory position, cover days, reorder point, safety stock, MOQ/pack rounding, and rule-based draft recommendations.
- **SP-3 Supplier and procurement workflow:** RFQ comparison, supplier scoring, approvals, PO, partial receipt, invoice matching, and exception queues.
- **SP-4 Forecast intelligence:** baselines, backtesting, seasonal/promotion features, confidence, forecast accuracy and drift monitoring.
- **SP-5 Network and financial optimization:** inter-branch transfers, cash/budget constraints, expiry-aware optimization, and scenario comparison.
- **SP-6 Controlled automation:** scheduled draft generation and notifications; any commitment remains behind human approval.

Each stage requires code, migrations, API/UI, audit and idempotency, negative authorization and concurrency tests, CI on the exact commit, and staging acceptance. This document is scope definition only and does not indicate implementation completion.

## Current implementation status (2026-11-08)

A first executable preview increment is present on branch `feat/smart-procurement-engine` (PR #11): deterministic demand baseline, censored stockout/promotion exclusion, safety-stock and reorder-point calculation, inventory-position arithmetic, MOQ/order-multiple handling, budget/storage/shelf-life/supplier-capacity constraints, supplier quote ranking, safe transfer suggestions, and a permission-gated preview API. Unit and API integration tests have been added.

This is **not** the complete module. The preview currently accepts demand, stock, supplier and source-branch facts from the caller; it does not yet load these from persistent tenant data or persist recommendations. Supplier/product master data, sales/POS event ingestion, real reservations and inbound purchase commitments, PO/RFQ workflow, approvals, receipts, invoice matching, accounting/valuation reconciliation, scheduled jobs, dashboards, and UI remain unimplemented. No CI run is currently visible for the PR head, so the integration tests and migration have not yet been verified in the repository's CI environment. Keep the PR in draft and do not merge or use this as production purchasing automation.
