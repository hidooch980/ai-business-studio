# OTP Service Core Implementation

## Implemented

`src/retail_app/security/otp.py` provides provider-agnostic OTP orchestration:
- six-digit codes generated with Python's operating-system CSPRNG;
- separate 32-byte-minimum peppers for identifier fingerprinting and code HMAC;
- challenge/purpose-bound HMAC, with no plaintext code in the receipt or persistence contract;
- five-minute expiry, 60-second resend timestamp, and five-attempt policy;
- E.164 phone and normalized email validation;
- generic, non-enumerating request receipt;
- explicit repository, delivery and rate-limiter ports;
- fail-closed behavior when rate limits deny or delivery fails; failed delivery invalidates the stored challenge;
- verification delegates atomic consume/attempt enforcement to the repository adapter.

## Mandatory production adapter contracts

The repository adapter must implement `create_challenge` as one transaction that invalidates prior active challenges and inserts the new challenge. `verify_and_consume` must lock the row (for example `SELECT ... FOR UPDATE`), validate purpose/expiry/attempt count, compare the candidate HMAC with `hmac.compare_digest` in application memory, increment failures atomically, and set `consumed_at` exactly once on success. Never perform read-then-write in separate transactions.

The rate limiter must be shared across application instances (e.g. Redis or a PostgreSQL-backed atomic limiter) and atomically enforce IP, device, identifier and global/provider-spend buckets. An in-process dictionary is not a production implementation.

The delivery adapter must use a verified SMS/email provider, must not log plaintext codes or full destinations, and must invalidate the challenge if delivery fails. The included unit tests use an in-memory fake only; no test code is configured as a production bypass.

## Not yet implemented

- PostgreSQL repository and transaction/RLS onboarding integration.
- Distributed rate-limiter implementation.
- Real SMS/email provider adapters and credentials.
- FastAPI challenge/verify/resend endpoints.
- Authenticated session creation, refresh rotation, logout and persistent security audit.
- End-to-end API tests and deployment configuration.

Do not enable production login until all missing adapters, secrets, RLS context handling, abuse controls and provider delivery have been implemented and verified.
