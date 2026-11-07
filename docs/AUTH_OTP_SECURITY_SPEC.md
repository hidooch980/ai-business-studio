# Authentication, OTP and Session Security Specification

Status: approved security design; runtime authentication and provider delivery are not yet implemented.

## 1. Authentication decision
- Primary sign-in: phone number plus one-time password (OTP).
- Alternate sign-in: verified email plus OTP where enabled by tenant policy.
- Customer, employee, manager and administrator identities use the same authentication service but distinct account types, permission policies and session scopes.
- Customer accounts are not workforce accounts. A customer cannot gain employee/manager privileges by changing profile fields or supplying a branch identifier.
- Password login is not required for the initial consumer experience. Optional passkeys/WebAuthn and enterprise SSO may be added later.
- OTP is for authentication and step-up verification; it is not a substitute for authorization, MFA policy or transaction approval.

## 2. Identifier handling
- Normalize phone numbers to E.164 before lookup or delivery.
- Verify ownership of phone/email before activating it as a login identifier.
- A user may have multiple verified identifiers, but identifier changes require re-verification and security notification.
- Never reveal whether an identifier is registered. Start/resend endpoints return a generic response with comparable timing.
- Apply tenant-independent global throttles as well as tenant/account limits to prevent enumeration and SMS pumping.
- Do not accept untrusted tenant, role, branch or account-type claims from the client.

## 3. OTP generation and lifecycle
- Generate cryptographically secure random six-digit codes using the operating system CSPRNG.
- Default expiry: five minutes. Each code is single-use and bound to the challenge, normalized identifier, purpose, account and delivery channel.
- Store only a keyed HMAC/hash of the OTP with a server-side secret pepper; never store or log the plaintext code.
- Compare in constant time. Invalidate previous active codes when a new code is issued, subject to resend policy.
- Default maximum verification attempts: five per challenge; invalidate on limit.
- Default resend cooldown: 60 seconds; enforce rolling hourly/daily limits per identifier, IP and device/risk bucket.
- Consume the challenge atomically on success to prevent concurrent replay.
- OTPs must not be accepted for a different purpose (login, identifier verification, recovery or step-up).
- Never include OTP in analytics, traces, crash reports, support logs or URLs.

## 4. Abuse prevention and delivery
- Rate-limit challenge creation and verification by identifier, IP, device signal and global provider spend.
- Use progressive cooldowns and risk-based challenges for suspicious traffic; avoid permanent lockout that enables denial of service.
- Detect SMS pumping, repeated delivery failures, unusual country/number ranges and high-cost destinations.
- Provider adapters support SMS and email with delivery status, timeout, retry policy and circuit breaker.
- Do not retry a delivery in a way that creates multiple simultaneously valid codes.
- Provider credentials live only in a secret manager/environment, never source control or client apps.
- For development, use a fake/local OTP provider that exposes test codes only in test fixtures; production must fail closed if a real provider is not configured.
- Never use a fixed OTP, universal backdoor code or production debug endpoint.

## 5. Session and token model
- After successful OTP verification, issue a server-managed session or short-lived access token with rotating refresh token.
- Web sessions use Secure, HttpOnly, SameSite cookies, CSRF protection for state-changing cookie-authenticated requests and session rotation after authentication/privilege changes.
- Mobile/PWA clients store refresh credentials only in platform secure storage where available; never localStorage for long-lived secrets.
- Session claims identify subject and session only; roles and branch scopes are reloaded/validated server-side and can be revoked.
- Support logout-current-session, logout-all-sessions, expiry, idle timeout, refresh-token rotation and reuse detection.
- Notify users of new-device sign-in and sensitive account changes where contact channel is available.
- High-risk actions (refund above limit, price override, loyalty adjustment, role change, payout/account change) require fresh step-up verification and explicit permission; OTP success alone does not authorize the action.

## 6. Recovery and identifier changes
- Recovery uses a verified alternate channel or a documented support process with identity checks and audit.
- Do not send OTP to a newly changed phone/email until the new identifier is verified.
- Sensitive identifier changes revoke other sessions or require explicit confirmation according to policy.
- Support staff cannot read OTP values or impersonate users without audited, time-limited break-glass authorization.
- Customer account deletion and data access requests follow applicable privacy and financial-record retention rules.

## 7. Authorization after authentication
- Enforce deny-by-default RBAC and resource ownership in backend services.
- Resolve tenant, branch, register and role scopes from trusted server-side records.
- Owner/admin, manager, employee and customer permissions are separate policy bundles.
- Every privileged operation checks actor, scope, amount/threshold, current resource state and reason requirements.
- Customer endpoints are restricted to the authenticated customer's own profile, points, coupons, orders and receipts.
- Manager and employee endpoints enforce assigned branch/register scope on every request.

## 8. Suggested API contract
- POST /api/v1/auth/otp/challenges — request a login/verification code.
- POST /api/v1/auth/otp/verify — verify challenge and establish session.
- POST /api/v1/auth/otp/resend — resend within cooldown and rate limits.
- POST /api/v1/auth/logout — revoke current session.
- POST /api/v1/auth/logout-all — revoke all sessions (step-up required).
- POST /api/v1/auth/refresh — rotate refresh credential.
- GET /api/v1/auth/sessions — list own active sessions.
- DELETE /api/v1/auth/sessions/{id} — revoke own selected session.
- POST /api/v1/auth/identifiers/verify — verify additional phone/email.
- POST /api/v1/auth/step-up — issue/verify step-up challenge for a declared purpose.
Responses must use generic challenge messaging to prevent account enumeration. API names are proposed and not yet implemented.

## 9. Audit and monitoring
Record challenge requested, delivery outcome, verification success/failure, throttling, lockout/cooldown, session creation/rotation/revocation, identifier changes, recovery and step-up outcomes.
Audit records include timestamp, actor/account reference where known, challenge/session ID, purpose, coarse risk metadata and outcome. Never record OTP plaintext, full tokens, secrets or unnecessary PII.
Alert on OTP abuse, delivery-cost spikes, repeated failures, refresh-token reuse and unusual session geography/device patterns.

## 10. Acceptance tests
1. OTP is generated from a CSPRNG, expires after configured TTL and is single-use.
2. Expired, incorrect, consumed and purpose-mismatched codes are rejected.
3. Concurrent verification cannot create multiple sessions from one challenge.
4. OTP plaintext and session secrets never appear in logs, traces or database.
5. Challenge/resend/verify limits prevent brute force and SMS pumping.
6. Unknown and known identifiers receive non-enumerating responses.
7. A customer cannot access employee, manager or other-customer data.
8. Changing client-supplied tenant/branch/role IDs cannot expand access.
9. Logout, session revocation and refresh-token reuse detection work.
10. High-risk actions require permission and step-up; successful OTP alone is insufficient.
11. Production startup fails closed when required signing/pepper/provider secrets are absent.
12. Tests use fake delivery adapters; no real SMS/email is sent by automated tests.

## 11. Rollout
- Auth foundation: identity schema, challenge store, rate limits, secure session and audit.
- Provider adapters: SMS and email, verified sender/domain and spend controls.
- Customer onboarding and customer app login.
- Employee and manager invitations, branch-scoped access and recovery.
- Step-up policy, session/device management, monitoring and penetration testing.
Production activation requires provider credentials, sender verification, privacy/legal review and operational alerting; none are assumed to exist.
