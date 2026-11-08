# Moadian integration

The Moadian module stores a tenant-scoped connection profile per tax-memory UID and supports two submission modes:

- `direct`: the taxpayer signs and submits using taxpayer-owned signing material.
- `tsp`: an approved tax-service provider submits through its own integration contract.

Only secret-manager references are stored in PostgreSQL. Private keys, certificates, API tokens, and passwords must never be sent to this API or committed to Git. The API response intentionally does not disclose secret references.

Each profile starts in the sandbox environment and disabled. Enabling a direct profile requires private-key and certificate references. Enabling a TSP profile requires a provider code and provider-credential reference. Tenant boundaries are enforced on every read and write.

## Current delivery boundary

This change establishes secure tenant configuration and schema for both modes. It does **not** yet send tax invoices or prove a live connection. The direct cryptographic transport, current official API contract, and each TSP's provider-specific API adapter must be implemented and tested against authorized sandbox credentials. The sales invoice domain is also a prerequisite for invoice mapping and submission. The API reports `awaiting_provider_adapter` rather than implying that a connection is live.

Before production activation:
1. Confirm the taxpayer's tax-memory UID and taxpayer identifier in the tax portal.
2. Provision secret-manager references through the deployment operator; never paste secret values into chat or ordinary application logs.
3. Validate current schema/version and tax rules against the official Tax Administration documentation.
4. Run sandbox send, status inquiry, duplicate/idempotency, rejection, correction, cancellation, and refund/return scenarios.
5. Obtain an explicit production enablement approval and preserve request/response audit evidence with sensitive fields redacted.

## References

- Tax Administration technical connection instruction: RC_TICS.IS_V01.
- Electronic invoice issuance instruction: RC_IITP.IS_V6.7.
