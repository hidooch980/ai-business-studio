# AI Smart Retail — Product and Delivery Roadmap

Status: approved roadmap; dates and release commitments are intentionally not assigned until capacity and dependencies are verified.

## Product surfaces
- Owner/admin web console.
- Manager application (responsive web/PWA initially).
- Employee application (role-based mobile-first PWA initially).
- Customer application (mobile-first PWA initially).
All clients use the same versioned API and identity platform. Native Android/iOS packaging is a later delivery track; no client keeps an independent source of truth.

## Phase 0 — trustworthy foundation
- FastAPI app factory, environment config, health/readiness, structured logs.
- PostgreSQL migrations, repository/service boundaries and typed API contracts.
- Tenant/store/branch/user model, authentication, RBAC, session controls and audit.
- CI lint/unit/integration tests; secrets and dependency scanning.
- Backup/restore runbook and migration rollback strategy.
Exit: reproducible build, passing CI, tenant isolation tests and tested restore.

## Phase 1 — operational retail core
- Product catalog, barcode/variants, tax and pricing history.
- POS, sales, returns, cash/card/online/split payments and idempotent callbacks.
- Cashier shifts, opening/closing and cash variance.
- Inventory ledger, purchase orders, supplier receiving, transfers and counts.
- Finance journal, expenses, receivables/payables and reconciliation.
- Manager and employee workflows for these operations.
Exit: payment/stock/journal invariants pass integration and concurrency tests.

## Phase 2 — customer relationship and loyalty
- Customer identity, consent, preferences and deduplication.
- Points ledger, versioned earn/burn/expiry/tier rules, coupons and rewards.
- Return reversal, referral anti-abuse, campaign budgets and redemption limits.
- Customer app: membership card, points, rewards, coupons, history and support.
- Employee app: customer lookup, eligible reward redemption and permission-gated overrides.
- Manager/admin: loyalty configuration, campaign preview, liability and campaign reporting.
Exit: no duplicate accrual/redemption under retries; all balances reconcile to ledger; consent and privacy tests pass.

## Phase 3 — reporting and command center
- Trusted operational reports and drill-downs from posted records.
- Owner/manager dashboards, branch comparisons, role-aware alerts.
- CSV/XLSX/PDF exports with audit and formula-injection protection.
- Financial Guard, Inventory Intelligence and sync/resilience health.
Exit: report totals reconcile to source ledgers; alert provenance and permissions verified.

## Phase 4 — AI assistance and forecasting
- Explainable demand forecasts with uncertainty and data sufficiency.
- Conversational manager assistant grounded only in authorized report/query tools.
- Anomaly detection for cash, discount, refund, margin and stock.
- Revenue opportunity finder and customer churn/loyalty insights.
Exit: shadow-mode evaluation, human review, model monitoring and rollback proven.

## Phase 5 — advanced decision support
- Decision Simulator for price, discount, order and cash-flow scenarios.
- Chain/root-cause detector linking purchasing, stock, POS, cash and margin.
- Branch transfer recommendations, workforce intelligence and advanced loyalty segmentation.
- Optional online storefront, delivery, marketplace and external accounting connectors.
Exit: impact estimates validated, approvals audited and no unauthorized execution path.

## Cross-cutting requirements
- Persian, English, Arabic and Turkish; RTL for Persian/Arabic.
- Single-store mode without unnecessary multi-branch complexity; multi-branch isolation and consolidated reporting.
- Offline-capable local POS with durable outbox/inbox and explicit conflict resolution.
- Accessibility, mobile-first UX, localization and observability.
- Append-only finance, inventory and loyalty ledgers.
- AI remains advisory; humans approve sensitive actions.

## Definition of done
A feature is done only when requirements, migrations, API, UI, permissions, audit, localization, automated tests, failure/retry behavior, documentation and operational monitoring are complete. A merged PR or green unit suite alone does not establish production readiness.
