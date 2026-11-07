# Loyalty Platform and Manager, Employee, Customer Applications

Status: approved product specification; implementation, provider integrations and production validation remain outstanding.

## 1. Product topology
Three client applications share one backend and canonical domain model:
- Admin/Owner console: web application for tenant owners and platform/store administrators.
- Manager application: responsive web/PWA for branch managers and supervisors.
- Employee application: mobile-first PWA for cashiers, sales associates, inventory staff and other scoped roles.
- Customer application: mobile-first PWA for members and shoppers.
The manager and employee experiences may share a codebase with role-specific navigation, but authorization is always enforced by the API. Customer identity is separated from workforce identity and never receives staff permissions.

## 2. Roles and permission model
- Platform operator: platform-level support only with explicit, audited break-glass access.
- Tenant owner: tenant configuration, billing/configuration if enabled, all authorized branches and reports.
- Tenant admin: users, roles, catalogs, policy configuration and integrations within tenant.
- Branch manager: assigned branch operations, staff, shifts, approvals and branch reports.
- Cashier/sales associate: POS, customer lookup and only explicitly allowed discounts/rewards.
- Inventory operator: receiving, counts, transfers and stock tasks within assigned locations.
- Accountant: finance, reconciliation and period-close permissions; no implied POS override.
- Customer/member: own profile, consent, points, coupons, orders and receipts only.
Permission checks include tenant, branch, register, action, amount/limit and resource ownership. Deny by default. Sensitive actions require reason codes and audit events. Never trust role or branch identifiers supplied by a client without resolving them against the authenticated principal.

## 3. Admin/owner console
- Business setup: tenant, stores, branches, registers, warehouses, currencies, tax, receipts and localization.
- User/role/permission administration, invitation, suspension, session revocation and access review.
- Catalog, price lists, supplier, purchasing and inventory configuration.
- POS/payment configuration and reconciliation status (credentials held in secrets vault/config, never exposed in UI).
- Finance, expenses, receivables/payables, cash/bank and period close.
- Staff, schedules, shifts, task assignment, commissions and payroll export.
- Loyalty configuration: earn/burn rules, tiers, rewards, coupons, campaigns, budgets, eligibility and exclusions.
- Reports and AI Command Center with drill-down and data freshness.
- Approvals inbox for refunds, overrides, stock adjustments, campaign activation and other configured high-risk operations.
- Audit log, sync health, backup/restore status and integration health.

## 4. Manager application
- Today view: sales, margin (only when cost data is complete), cash status, open shifts, stock alerts and pending approvals.
- Branch performance and comparisons limited to authorized branches.
- Staff roster, shift handover, attendance exceptions, tasks and announcements.
- Purchase requests, receiving exceptions, stock counts and inter-branch transfer requests.
- Customer/loyalty insights with consent-aware visibility; no unrestricted export of personal data.
- Campaign preview and performance; manager can activate only if policy grants permission.
- Exception workflow: refund/void/discount/cash variance/stock adjustment approval with evidence and reason.
- Offline status and sync conflict queue visibility.
Managers cannot change posted ledger entries or bypass owner/admin policy.

## 5. Employee application
- Secure sign-in, assigned store/branch/register and shift start/end.
- POS sale flow: scan/search, cart, customer association, permitted discount, payment tender and receipt.
- Customer membership lookup by QR/member code or consented phone lookup; avoid exposing full customer profile.
- Earn preview and reward redemption with eligibility, available points and confirmation.
- Product lookup, stock availability, receiving/counting/transfer tasks for authorized roles.
- Sales attribution, task checklist, announcements and personal shift/sales summary.
- Refund/void/price override only when explicitly authorized; mandatory reason and approval when threshold exceeded.
- No visibility into payroll of others, tenant-wide financial reports, secrets or unrelated customer data.

## 6. Customer application
- Registration/sign-in with verified contact method; guest checkout may be supported without forced membership.
- Digital membership QR/barcode with rotating or signed token; do not encode personal data in the code.
- Points balance, transaction history, tier, progress to next tier, expiry warnings and reward catalog.
- Coupon wallet, eligibility details, expiry, branch/product restrictions and redemption history.
- Offers and personalized recommendations only with lawful basis and communication consent.
- Purchase/order history, digital receipts, return eligibility and support requests.
- Profile, language, accessibility, notification preferences, consent management and account deletion request workflow.
- Optional wishlist, saved products, store locator and online ordering/delivery when those modules are enabled.
- Clear disclosure that points/rewards are not cash unless a jurisdiction-specific approved stored-value product is separately implemented.

## 7. Loyalty domain model
Core entities (logical; physical schema to be designed with migrations):
- LoyaltyProgram: tenant, status, currency context, policy version, valid branches and program terms.
- Member: customer reference, member number, status, joined_at, consent references and deduplication links.
- PointsAccount: member, program, available/pending/expired totals as derived projections; ledger remains authoritative.
- PointsLedgerEntry: immutable event ID, member/program, signed points, event type, source sale/return/redemption/campaign, rule version, expiry, actor, timestamp and idempotency key.
- TierDefinition and TierHistory: thresholds, evaluation window, benefits and effective dates.
- Reward and Coupon: eligibility, value/type, budget, issue/redeem limits, branch/product constraints, validity and stacking policy.
- Campaign: audience definition, channels, consent, budget cap, schedule, frequency cap and attribution window.
- Referral: referrer/referee, qualifying event, anti-abuse state and reward ledger references.
- Redemption: quote/reservation/commit/reversal lifecycle and source POS/order.
- ConsentRecord and CommunicationEvent: purpose, channel, legal basis/consent version, timestamp and opt-out state.

## 8. Earn, burn, tier and expiry policy
- Configure earn rate by eligible net merchandise subtotal; tax, shipping, fees, gift cards, excluded categories and discounted items are explicit.
- Define rounding (prefer integer points and deterministic rounding), minimum eligible basket, maximum earn per order/day and campaign stacking.
- Points accrue only from finalized/posted eligible sales. Pending accrual may be used during a payment/return window if configured.
- Define redemption value, minimum balance, maximum share of basket, eligible branches/items, and whether redemption can combine with coupons.
- Reserve points atomically during checkout; commit only when payment/sale is finalized; release reservation on cancellation/timeout.
- Tier evaluation uses a declared rolling or calendar window and a versioned policy; tier downgrade/upgrade notifications are configurable.
- Expiry is per-lot or per-entry with a disclosed policy, deterministic expiry job and customer notification.
- Return/cancel reverses earned points attributable to returned items. If redeemed benefits were used, apply a documented recovery rule; never silently create negative balances.
- Manual adjustments require permission, reason, source reference and dual approval above configured thresholds.
- Rule changes are versioned and effective-dated; existing ledger entries retain the rule version that created them.

## 9. Fraud and abuse controls
- Idempotency and unique source-event constraints prevent duplicate earn, referral or redemption.
- Rate limits and risk checks for sign-up, phone verification, QR scans, referrals and coupon claims.
- Detect repeated accounts/devices/payment instruments only within lawful privacy limits; do not make irreversible decisions solely from a risk score.
- Block self-referral, circular referral and repeated qualifying-event abuse using transparent policy.
- Require online validation for high-value redemption; offline redemption has a strict configurable low-risk ceiling or is disabled.
- Manager/admin manual grants are audited and anomaly-monitored.
- Customer disputes have a traceable review process; fraud flags are not proof of misconduct.

## 10. Proposed API surface
Customer:
- GET /api/v1/me
- GET /api/v1/me/loyalty
- GET /api/v1/me/loyalty/ledger
- GET /api/v1/me/rewards
- GET /api/v1/me/coupons
- POST /api/v1/me/coupons/{id}/claim
- GET /api/v1/me/orders
- GET/PATCH /api/v1/me/preferences
Employee/POS:
- GET /api/v1/pos/customers/lookup
- POST /api/v1/pos/loyalty/quote
- POST /api/v1/pos/loyalty/redemptions/reserve
- POST /api/v1/pos/loyalty/redemptions/{id}/commit
- POST /api/v1/pos/loyalty/redemptions/{id}/release
Manager/admin:
- GET /api/v1/admin/loyalty/program
- POST /api/v1/admin/loyalty/rules (versioned)
- POST /api/v1/admin/loyalty/campaigns
- GET /api/v1/admin/loyalty/analytics
- POST /api/v1/admin/loyalty/adjustments (permission and approval gated)
All endpoints require tenant scoping, ownership checks, pagination, validation, rate limits, audit and idempotency where commands mutate state. Endpoint list is proposed, not implemented.

## 11. Notifications and messaging
- In-app inbox is the canonical notification history.
- Push, email and SMS are optional providers with delivery status, retry and opt-out enforcement.
- Transactional messages (receipt, points earned, reward redeemed, expiry reminder) are separated from marketing messages.
- Frequency caps, quiet hours, locale and consent are enforced centrally.
- Never send payment secrets, full card data or unnecessary personal details.

## 12. Analytics and KPIs
- Active members, new members, repeat purchase rate, purchase frequency and member retention/cohort.
- Points issued, redeemed, expired, outstanding liability and breakage (subject to accounting/legal review).
- Redemption rate, reward cost, incremental margin and campaign ROI with attribution assumptions.
- Tier migration, referral conversion and coupon abuse indicators.
- Employee/branch loyalty redemption and enrollment performance with role-based access.
- All KPIs disclose time window, source, currency, data freshness and methodology. Do not claim incremental lift without a valid comparison/experiment design.

## 13. Security, privacy and reliability
- Customer and workforce identity domains are logically separated; MFA/passkeys may be added.
- Encrypt transport and sensitive stored fields; minimize PII; redact logs and analytics.
- Consent is purpose-specific, timestamped and revocable; marketing opt-out must propagate to providers.
- Data access/export/deletion workflows follow applicable law and retention obligations; financial/audit records follow legal retention rules.
- Tenant and branch authorization is server-side; QR/member tokens are signed, short-lived or rotating, and replay-protected.
- Offline events are durable and idempotent; points redemption should be online by default unless strict offline limits are configured.
- Backups, restore drills, monitoring and incident response cover all ledgers and outbox queues.

## 14. Acceptance tests
1. A cashier cannot view another branch's customer/finance data without permission.
2. Customer A cannot read or mutate Customer B's profile, coupons, points or orders.
3. Retried sale finalization cannot award points twice.
4. Concurrent redemptions cannot spend the same points twice.
5. Return reverses the correct earned points and links to original sale lines.
6. Expiry runs once effectively and records the policy version.
7. Coupon stacking, branch scope, budget, time window and eligibility are enforced server-side.
8. Rule changes do not rewrite historical accruals.
9. Offline sync does not duplicate ledger entries; high-risk redemption obeys offline policy.
10. Consent withdrawal suppresses future marketing messages across all configured channels.
11. Manual point adjustment requires reason, authorization and audit; high-value adjustments require dual control.
12. Customer app never exposes staff/admin endpoints or secrets.
13. All three app surfaces pass responsive, accessibility, localization and RTL checks.
14. Loyalty analytics reconcile to immutable ledger entries and clearly label estimates.

## 15. Release sequence
- L0: customer/employee identity boundaries, consent, permissions and event contracts.
- L1: points ledger and deterministic earn/burn/reversal engine.
- L2: employee POS integration and manager approval/configuration.
- L3: customer app membership, points, coupons and receipts.
- L4: tiers, campaigns, referrals, notifications and analytics.
- L5: fraud analytics and AI-personalized offers (advisory and consent-aware).
