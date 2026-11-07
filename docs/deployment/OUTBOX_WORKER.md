# Transactional outbox worker

The API writes inventory outbox events in the same transaction as stock movements. The worker uses leased batches and at-least-once delivery: handlers must be idempotent because a process can stop after an external side effect but before the delivery acknowledgement commits.

## Configure a handler package

Deploy a Python module that exposes a zero-argument factory returning a non-empty dictionary of event type to handler callables:

```python
from backend.app.outbox.worker import OutboxMessage


def handle_inventory_movement(db, message: OutboxMessage) -> None:
    # Validate the payload and use a stable idempotency key with any provider.
    # Keep database work in this session; do not commit inside the handler.
    ...


def build_handlers():
    return {"inventory.movement.created": handle_inventory_movement}
```

Set `OUTBOX_HANDLER_FACTORY=your_package.outbox_handlers:build_handlers`. The module must be installed in the worker virtual environment. The worker refuses to start if the factory is missing, invalid, or returns an empty registry. Unknown event types are retried and eventually moved to dead-letter state; do not start the worker until the registry covers every event type expected in that environment.

## systemd installation

1. Create a dedicated `abs-app` service account and install the application and virtual environment under `/opt/ai-business-studio`.
2. Install `deploy/systemd/ai-business-studio-outbox.service` into `/etc/systemd/system/`.
3. Create `/etc/ai-business-studio/worker.env`, owned by root and readable only by the service group, with at least:

   ```ini
   DATABASE_URL=postgresql+psycopg://...
   OUTBOX_HANDLER_FACTORY=your_package.outbox_handlers:build_handlers
   OUTBOX_BATCH_SIZE=50
   OUTBOX_POLL_INTERVAL_SECONDS=2
   LOG_LEVEL=INFO
   ```

4. Ensure the database role has only the privileges needed by the worker and handler integrations. Keep provider credentials in the protected environment file or a secret manager; never commit them.
5. Run `systemd-analyze verify` on the unit, then enable it only after staging handler contract tests pass:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now ai-business-studio-outbox.service
   sudo systemctl status ai-business-studio-outbox.service
   ```

The worker handles SIGTERM/SIGINT by stopping after the current batch. It restarts on failure. This template does not yet provide a dedicated readiness endpoint, metrics, alerting, or a concrete provider adapter. Those remain operational release gates.
