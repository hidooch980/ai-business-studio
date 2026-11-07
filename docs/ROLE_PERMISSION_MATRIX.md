# Role Permission Matrix and Workspace UX Contract

Status: approved product contract and frontend preview. This document is not a substitute for runtime authorization; backend enforcement is not implemented by the UI.

## Global rules

- Deny by default. A hidden navigation item is never an authorization control.
- Every request must be authorized server-side against tenant, active role, branch membership, resource and action.
- Customer identity is separate from workforce identity.
- Role switching in the preview is a design demonstration only. Production role/context switching must use server-issued memberships and must not elevate privileges.
- High-risk operations require explicit permission, reason capture and, where configured, a second approver.
- Financial, inventory and loyalty ledgers are append-only; corrections use linked reversal/adjustment entries.
- Sample values and local preview state must never be presented as live business data.

## Permission matrix

Legend: **Own** = own records only; **Assigned** = assigned branch/tasks; **Scoped** = authorized tenant/branch scope; **Approve** = only within explicit approval policy; **No** = denied by default.

| Capability | Owner/Admin | Branch manager | Employee | Customer |
|---|---|---|---|---|
| Business-wide overview | Scoped | No | No | No |
| Branch overview | Scoped | Assigned | No | No |
| User invitations and role assignment | Scoped | No by default | No | No |
| POS sale creation | Scoped | Assigned | Assigned, permission-gated | No |
| Discounts / price overrides | Approve / policy | Approve / policy | No by default | No |
| Refunds and returns | Approve / policy | Approve / threshold | No by default | Request/support only |
| Inventory read | Scoped | Assigned | Assigned | No |
| Inventory adjustment / write-off | Approve / policy | Approve / threshold | No by default | No |
| Purchase request | Scoped | Assigned | No by default | No |
| Purchase order approval | Approve / policy | Approve / threshold | No | No |
| Cash shift open/close | Scoped | Assigned | Assigned | No |
| Finance reports | Scoped | Assigned summary only | No | No |
| Payroll and commissions | Scoped | Assigned summary only | No | No |
| Customer profile | Scoped | Assigned | Minimum required | Own |
| Loyalty balance and rewards | Scoped | Assigned support view | Minimum required | Own |
| Loyalty manual adjustment | Approve / dual control | No by default | No | No |
| Personal receipts and order history | Support access with audit | Support access with audit | Minimum required | Own |
| AI recommendations | Scoped review | Branch scoped review | No by default | No |
| Approve sensitive AI action | Approve / policy | Approve / threshold | No | No |
| Audit trail | Scoped | Assigned operational events | Own actions only | Own account events |
| Session management | Scoped administration | No by default | Own sessions | Own sessions |

This is a conservative default matrix. Tenant owners may delegate only through explicit permission grants, thresholds and branch scopes. Customer-facing access must never expose workforce administration or other customers' data.

## Frontend preview behavior

The role workspace currently demonstrates four navigation sets, role-specific sample cards, a local global-search index, a local approval inbox, dismissible sample notifications and in-memory widget visibility controls.

These controls are deliberately local:
- Search filters a static role-tagged index and does not query a backend.
- "Mark reviewed" changes only local preview state; it does not approve a transaction.
- Dismissing a notification affects only the current page session.
- Dashboard widget choices are in-memory and are not persisted to a user profile.
- The role switcher is not authentication, authorization or tenant switching.

## Required backend contracts before production

- Resolve active tenant, membership, role and branch scope from authenticated server-side identity.
- Enforce action-level permissions on every API and data query.
- Provide paginated, scoped search with explicit resource permissions and audit-safe results.
- Provide durable notification delivery/read state and approval lifecycle APIs with idempotency.
- Persist per-user dashboard preferences with schema validation and safe defaults.
- Record approval actor, policy, reason, timestamps and before/after references.
- Add authorization tests for allow, deny, cross-tenant, cross-branch, revoked-session and stale-context cases.

## Acceptance checks

1. All four role previews render without a runtime exception.
2. Switching role resets the active navigation to that role's first route.
3. Search returns only entries assigned to the selected role; empty search shows no results panel.
4. Search has a clear action and keyboard-accessible label.
5. Approvals can be marked reviewed only in local preview state and remain visibly labelled as sample.
6. Notification dismissal updates the current preview list without claiming server persistence.
7. Widget visibility controls show/hide the metric cards, approval panel and notification panel.
8. Customer view does not render the approval panel.
9. Narrow viewport layout stacks search, controls and panels without horizontal overflow.
10. No action claims a payment, refund, stock mutation, real approval or permission change succeeded.
