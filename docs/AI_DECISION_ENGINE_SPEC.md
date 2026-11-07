# AI Decision Engine — Architecture and Safety Specification

Status: approved design specification; no autonomous execution is authorized.

## Purpose
Provide one explainable recommendation service across retail domains. It consumes authorized, tenant-scoped business facts and produces evidence-backed recommendations for people. It is not a replacement for accounting, inventory controls, authorization or human judgment.

## Initial decision domains
- Financial Guard: settlement mismatch, unusual discounts/refunds/voids, cash variance, overdue balances, margin leakage and suspicious expense patterns.
- Inventory Intelligence: reorder/stockout risk, dead stock, shrinkage anomalies, expiry risk where tracked and transfer opportunities.
- Command Center: consolidated sales, margin, cash, stock, staff and branch alerts with freshness indicators.
- Later domains: demand forecasting, conversational analytics, price/discount simulator, revenue opportunities, chain/root-cause analysis, customer churn/loyalty and workforce intelligence.

## Logical architecture
1. Event/fact adapters read posted sales, payments, journals, stock movements, shifts, customer consent and sync-health records.
2. Feature and metric layer creates versioned, reproducible features; records source watermark, time window, currency, timezone and data quality.
3. Policy/rule engine evaluates deterministic hard constraints before statistical or model scoring.
4. Model registry stores model name/version, training window, feature schema, validation metrics and deployment status.
5. Decision evaluator combines rule outcomes, model output, confidence/calibration and expected impact.
6. Recommendation store persists immutable recommendation versions and lifecycle events.
7. Approval workflow routes to a user with the required permission and branch scope.
8. Execution adapters are separate domain commands; no direct database writes from AI. Every command revalidates authorization, state, limits and idempotency.
9. Audit/monitoring tracks outcomes, false positives, drift, stale inputs, model health and operator feedback.

## Recommendation contract
Each recommendation must include unique recommendation_id and idempotency key; tenant_id and permitted branch scope; domain, category, severity and concise title; evidence references to source record IDs/aggregates; observation window and generated_at timestamp; data freshness and quality flags; proposed action and alternatives; confidence plus calibration/meaning label; estimated financial/operational impact with currency, assumptions and range; rule/model versions and explanation; expiry time, status and required permission/approval level.

## Lifecycle
detected -> evaluated -> pending_review -> approved | rejected | expired | superseded -> executed | execution_failed -> outcome_recorded.
Transitions are append-only. Rejection captures an optional reason; approval captures actor, time, scope and policy version. Repeated identical alerts are deduplicated by tenant, branch, rule and time window. Material evidence changes create a new version rather than mutating history.

## Safety boundaries
- AI cannot autonomously issue refunds, capture/transfer money, change prices, post journals, write off stock, create purchase orders, redeem points or alter payroll.
- AI cannot expand a user's permissions or cross tenant/branch boundaries.
- High-risk suggestions require explicit human approval; execution rechecks current data and permissions.
- No model output may bypass deterministic payment, inventory, accounting or loyalty invariants.
- If evidence is stale, incomplete, contradictory or below minimum sample thresholds, suppress or label the recommendation as insufficient data.
- Never use customer sensitive data beyond stated purpose/consent; minimize and redact prompt/context payloads.
- External LLM providers receive only minimized, policy-approved context; secrets and payment data are prohibited.

## Decision classes
- Informational: descriptive insight only.
- Advisory: suggests action, no mutation.
- Approval-required: can create a pending command only after human approval.
- Prohibited: autonomous high-impact actions listed above.

## APIs (proposed)
- GET /api/v1/ai/decisions
- GET /api/v1/ai/decisions/{id}
- POST /api/v1/ai/decisions/{id}/approve
- POST /api/v1/ai/decisions/{id}/reject
- POST /api/v1/ai/decisions/{id}/feedback
- GET /api/v1/ai/health
All endpoints enforce tenant/branch scope, RBAC, pagination, audit and idempotency. Approval records approval; a separate domain command performs any permitted action.

## Data governance and model operations
- Version feature definitions, rules, prompts and models.
- Log model inputs by reference and safe feature snapshot, not raw sensitive payload.
- Validate accuracy, calibration, bias, drift and subgroup impact before promotion.
- Require human-reviewed offline evaluation and shadow mode before enabling recommendations.
- Roll back model/rule versions without deleting prior decisions.
- Define retention, deletion and legal basis per jurisdiction.
- Record recommendation outcome and compare predicted vs realized impact.

## Acceptance tests
1. Cross-tenant and cross-branch requests are denied.
2. Duplicate events produce one effective recommendation and no duplicate action.
3. Stale or insufficient data suppresses or clearly labels output.
4. Every recommendation is explainable and traceable to source evidence and rule/model versions.
5. No AI endpoint can directly mutate money, stock, price, points or payroll.
6. Approval requires authorized actor, reason where required, and fresh state validation.
7. Rejected/expired/superseded recommendations cannot execute.
8. Model rollback preserves historical audit records.
9. Prompt injection in customer/product/supplier text is treated as untrusted data, never as policy.
10. Monitoring detects drift, failure spikes and stale source watermarks.
