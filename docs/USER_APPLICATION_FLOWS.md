# User Application Flows and Navigation

Status: product UX specification; these flows are not yet connected to runtime APIs.

## Identity and entry

1. User opens the public site or app.
2. User chooses phone or verified email.
3. Backend creates a purpose-bound OTP challenge and delivery provider sends it.
4. User submits the code; backend atomically verifies and consumes the challenge.
5. Backend resolves identity, tenant membership, role and branch scope.
6. User lands in the permitted workspace. If multiple businesses/branches are available, show only authorized choices.
7. If provider configuration is missing, fail closed with a safe, actionable message. Never provide a universal code or expose OTP in logs.

## Role landing routes

| Role | Default route | Main navigation |
|---|---|---|
| Owner/Admin | /app/overview | Overview, branches, users, finance, reports, approvals, settings |
| Manager | /app/branch | Branch overview, POS, inventory, purchasing, staff, reports |
| Employee | /app/work | POS/tasks, customers, shifts, permitted stock actions |
| Customer | /customer/home | Membership, rewards, coupons, receipts, support, privacy |

A user with multiple roles must use an explicit active role/context; do not silently elevate permissions.

## Admin user lifecycle

- Invite user → select role → assign tenant and branch scope → send invitation/OTP → user verifies → membership becomes active.
- Change role/scope → require authorized actor and audit record → invalidate or refresh affected sessions according to security policy.
- Suspend/deactivate → block future requests server-side → optionally revoke all sessions.
- Session review → show device/session metadata with safe masking → revoke one or all sessions.

## POS sale lifecycle

- Open register and shift → scan/search items → validate current price and stock policy → optionally attach customer → apply authorized discount → select payment method(s) → backend finalizes sale → receipt becomes available.
- A failed or pending payment must not be represented as paid.
- A retry must use an idempotency key to avoid duplicate sales or charges.
- Refund/return creates linked reversal records; it does not erase the original sale.
- Offline sale must be clearly queued and reconciled using server-defined conflict rules.

## Loyalty customer lifecycle

- Customer consents to enrollment → membership created → eligible completed sale earns points through a versioned rule.
- Redemption checks available balance and eligibility atomically.
- Return reverses points associated with returned sale lines.
- Customer sees ledger history, expiry and coupon terms.
- Manual adjustments require permission, reason and audit trail.

## AI recommendation lifecycle

- Recommendation generated with evidence, source freshness, confidence, model/rule version and expiry.
- User inspects details and expected impact.
- Authorized user approves or rejects with optional reason.
- Sensitive business changes are executed only by a separately permissioned workflow and recorded in audit history.
- Expired or duplicate recommendations are clearly labelled and cannot be approved as current.

## Navigation and permission contract

- Frontend routes are usability boundaries, not security boundaries.
- Backend authorization is enforced on every request using tenant, branch, role and action permission.
- Unauthorized route access returns a safe forbidden/not-found experience without leaking record existence.
- Switching branch updates context and refetches scoped data; stale data from the previous branch must not remain visible.
- Deep links must re-check permissions after login and after context changes.

## UX acceptance checklist

- OTP cannot be replayed, reused for another purpose or used after expiry.
- Account enumeration is prevented by neutral responses.
- Role and branch switching never grants broader access.
- Critical writes provide pending/success/failure feedback based on backend results.
- Duplicate submissions are guarded by idempotency.
- Offline and sync states are explicit.
- Customer identity is isolated from staff identity.
- All user-visible strings are localizable and support RTL/LTR.
