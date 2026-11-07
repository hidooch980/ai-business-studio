# Backend Authorization Core

Status: implemented policy primitive with automated unit tests. This is not yet a complete authentication or production authorization service.

## What is implemented

- Immutable server-side `AccessContext` and resource scope contracts.
- Deny-by-default role permission bundles for owner/admin, branch manager, employee and customer.
- Tenant boundary checks for every authorization decision.
- Branch membership enforcement for manager and employee operations.
- Customer ownership checks for customer self-service resources.
- Inactive or incomplete identities are rejected.

## Security integration contract

1. Authentication middleware must resolve the subject and active session from trusted server-side records.
2. Membership lookup must resolve tenant, role and branch memberships from the database; never accept these values from request JSON or query parameters.
3. Every service method must call `authorize` before reading or mutating a resource, and database queries must independently include tenant/branch/owner filters.
4. Do not treat frontend navigation hiding or role switching as security controls.
5. Sensitive actions still require explicit approval policy, thresholds, reason capture and audit events. This module does not approve refunds, discounts, payments, inventory adjustments or loyalty mutations.
6. Add a persistence-backed membership/session model and API dependency layer before exposing protected HTTP endpoints.

## Explicit limitations

- No FastAPI application, database models, migrations, OTP challenge flow, SMS/email provider, session issuance, refresh rotation, audit persistence or API routes are introduced here.
- Permission bundles are conservative starting defaults and must be reviewed against tenant policy before production.
- Passing these unit tests does not constitute a penetration test or production security certification.
