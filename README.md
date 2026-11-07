# AI Business Studio

A modular, offline-capable retail management platform for single-store and multi-branch businesses in Iran and international markets.

## Approved product scope

General-purpose retail for grocery, apparel, electronics, home goods, mobile, parts and other retail categories.

### Applications
- Secure OTP sign-in (phone primary, verified email alternate), role-scoped sessions and audit
- Owner/admin web console
- Branch manager application
- Role-based employee application (cashier, sales, inventory and operations)
- Customer application/PWA with membership, rewards, coupons, receipts and support

All applications share one backend and source of truth, with strict role, tenant and branch authorization.

### Business capabilities
- POS, barcode/QR, sales, returns and cash/card/online/split payments
- Catalog, variants, pricing and tax configuration
- Inventory, warehouses, stock ledger and transfers
- Purchasing, suppliers and goods receiving
- Retail finance, cash/bank, receivables/payables and reconciliation
- Staff shifts, tasks, commissions and payroll export
- Customer CRM and loyalty: points ledger, tiers, rewards, coupons, campaigns and referrals
- Single-branch and multi-branch management
- Offline-capable operation and durable synchronization
- Reporting, BI and explainable advisory AI

Manufacturing, industrial maintenance, fleet management, project management and enterprise HR are excluded from the retail core.

## Product specifications
- [Approved retail product scope](docs/RETAIL_PRODUCT_SCOPE.md)
- [Loyalty and manager/employee/customer applications](docs/LOYALTY_AND_APPS_SPEC.md)
- [OTP authentication and session security](docs/AUTH_OTP_SECURITY_SPEC.md)
- [Backend authorization core and integration contract](docs/BACKEND_AUTHORIZATION_CORE.md)
- [PostgreSQL identity and security schema](docs/POSTGRES_IDENTITY_SECURITY_SCHEMA.md)
- [AI Decision Engine specification](docs/AI_DECISION_ENGINE_SPEC.md)
- [AI retail product roadmap](docs/AI_AUTONOMOUS_RETAIL_ROADMAP.md)
- [Reporting and BI specification](docs/REPORTING_AND_BI_SPEC.md)
- [Reporting implementation backlog](docs/REPORTING_IMPLEMENTATION_BACKLOG.md)
- [Acceptance and verification plan](docs/RETAIL_ACCEPTANCE_TEST_PLAN.md)

## Frontend foundation

A first responsive React + TypeScript + Vite UI prototype lives in `frontend/`.
- Public landing page with retail capability and security sections.
- OTP entry screen clearly marked as not connected to a delivery/API provider.
- Role-oriented admin dashboard shell with explicitly labelled sample data.
- Responsive desktop/mobile layouts and RTL-first Persian UI.
- Four role-specific workspace previews: owner/admin, branch manager, employee and customer.
- Local preview tools for role-filtered search, sample notifications, approval review markers and dashboard widget visibility.
- Frontend CI type-checks and builds the Vite app.

A backend authorization policy primitive enforces deny-by-default role permissions, tenant isolation, branch membership and customer ownership at service boundaries; a PostgreSQL identity/session/OTP/audit schema migration is authored but not yet applied to a live database. See [backend authorization core](docs/BACKEND_AUTHORIZATION_CORE.md) and [PostgreSQL identity/security schema](docs/POSTGRES_IDENTITY_SECURITY_SCHEMA.md). This is not a complete authentication/session/API service. The role workspace tools are local UI demonstrations only. Search uses a static index; notification and approval state is in-memory; dashboard preferences are not persisted. Authentication, backend APIs, live data, payment flows, durable approvals/notifications, user preferences and server-side role authorization still require implementation and integration. See [role permission matrix and workspace UX contract](docs/ROLE_PERMISSION_MATRIX.md).

## UX/UI design foundation

- [UX/UI design system and role workspaces](docs/UX_UI_DESIGN_SYSTEM.md)
- [User application flows and navigation](docs/USER_APPLICATION_FLOWS.md)

## Architecture decisions

- **Backend:** Python and FastAPI.
- **Architecture:** modular monolith with explicit domain boundaries and versioned contracts.
- **Central database:** PostgreSQL.
- **Local/offline mode:** SQLite in WAL mode on a single local node; never share a SQLite database file over a network filesystem.
- **API:** versioned REST endpoints under /api/v1.
- **Ledgers:** append-only finance, inventory and loyalty records; corrections use reversal/adjustment entries.
- **Multi-tenancy:** tenant- and branch-scoped data access and authorization checks at service boundaries.
- **Synchronization:** transactional outbox/inbox, idempotency keys, retry handling and explicit conflict resolution.
- **AI:** advisory only; sensitive actions require authorized human approval.
- **Localization:** Persian, English, Arabic and Turkish; RTL for Persian/Arabic.

## Repository status

This repository is at specification/bootstrap stage. Documented scope is not evidence that runtime features are implemented or production-ready. Implementation, automated tests, security verification and release checks are required before a stable release can be claimed.

## Delivery sequence

1. Application foundation, configuration, health, migrations, CI and security baseline.
2. Tenant/store/branch/user/access model.
3. Catalog, POS, payments, returns and cash shifts.
4. Inventory, purchasing and finance ledger.
5. Customer identity, consent and loyalty engine.
6. Manager, employee and customer application workflows.
7. Reporting, multi-branch synchronization and offline recovery.
8. AI decision engine and advisory modules.
9. Localization, hardening, end-to-end tests and release packaging.

## Security

Do not commit credentials, API tokens, private keys, signing keys, customer data, payment-card data, production database files, backups, logs or environment files. Use GitHub Actions Secrets or an approved secret manager for deployment credentials.

Report suspected vulnerabilities privately to the repository owner. See [SECURITY.md](SECURITY.md).

## License

No license has been selected yet. Until one is added, the default copyright rules apply; do not assume the code is available for unrestricted reuse.
