# Transactional outbox foundation

## Purpose

Business writes must not commit while silently losing the event needed by a later notification, integration, or workflow. The outbox row is inserted in the same database transaction as the business operation. The current first integration is inventory movement creation.

## Event lifecycle

- `pending`: eligible after `available_at`.
- `processing`: leased to one worker with `locked_by`, `locked_until`, and an unguessable `lease_token`.
- `delivered`: acknowledged by the current lease token.
- `dead_letter`: retry budget exhausted and operator intervention required.

Claims use row-level `FOR UPDATE SKIP LOCKED` on PostgreSQL. Expired leases can be reclaimed. A stale worker cannot acknowledge or retry an event after another worker has acquired a new lease.

## Service contract

- `enqueue_outbox_event`: tenant-scoped deduplication by `dedupe_key`; a replay with the same event payload returns the existing row, while a different payload is rejected.
- `claim_outbox_events`: claims a bounded batch and commits a lease before returning.
- `mark_outbox_delivered`: accepts only the current lease token.
- `retry_outbox_event`: schedules a retry or moves the event to `dead_letter` after the configured attempt limit.

## Delivery semantics and limitations

The outbox provides durable at-least-once dispatch, not exactly-once external side effects. Consumers must use the event ID as an idempotency key when calling external providers. The current repository has not yet added a continuously running worker, handler registry, provider adapters, notifications, approval workflows, metrics, or operator replay UI. Do not claim external delivery based solely on an event being enqueued.
