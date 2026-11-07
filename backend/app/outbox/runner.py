from __future__ import annotations

import importlib
import logging
import os
import signal
import socket
import threading
from types import ModuleType

from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.session import get_session_factory
from backend.app.outbox.worker import OutboxHandler, run_outbox_batch

LOGGER = logging.getLogger("ai_business_studio.outbox")


def load_handlers(factory_path: str) -> dict[str, OutboxHandler]:
    """Load a deployment-owned handler factory using module:callable syntax."""
    module_name, separator, attribute = factory_path.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise ValueError("OUTBOX_HANDLER_FACTORY must use the module:callable format")
    module: ModuleType = importlib.import_module(module_name)
    factory = getattr(module, attribute, None)
    if not callable(factory):
        raise ValueError("Configured outbox handler factory is not callable")
    handlers = factory()
    if not isinstance(handlers, dict):
        raise ValueError("Outbox handler factory must return a dictionary")
    for event_type, handler in handlers.items():
        if not isinstance(event_type, str) or not event_type.strip() or not callable(handler):
            raise ValueError("Outbox handlers must map non-empty event types to callables")
    if not handlers:
        raise ValueError("Outbox handler registry cannot be empty")
    return handlers


def run_worker_loop(
    session_factory: sessionmaker[Session],
    *,
    worker_id: str,
    handlers: dict[str, OutboxHandler],
    stop_event: threading.Event,
    poll_interval_seconds: float = 2.0,
    batch_size: int = 50,
) -> None:
    if not worker_id.strip() or not 0.1 <= poll_interval_seconds <= 300 or not 1 <= batch_size <= 200:
        raise ValueError("Invalid outbox worker configuration")
    while not stop_event.is_set():
        try:
            result = run_outbox_batch(
                session_factory,
                worker_id=worker_id,
                handlers=handlers,
                limit=batch_size,
            )
            if result["claimed"]:
                LOGGER.info("Outbox batch completed: %s", result)
            else:
                stop_event.wait(poll_interval_seconds)
        except Exception:
            LOGGER.exception("Outbox batch failed; worker will retry")
            stop_event.wait(min(poll_interval_seconds * 2, 60))


def _positive_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    factory_path = os.getenv("OUTBOX_HANDLER_FACTORY", "").strip()
    if not factory_path:
        raise RuntimeError("OUTBOX_HANDLER_FACTORY must be configured; refusing to start without handlers")
    handlers = load_handlers(factory_path)
    try:
        poll_interval = float(os.getenv("OUTBOX_POLL_INTERVAL_SECONDS", "2"))
    except ValueError as exc:
        raise ValueError("OUTBOX_POLL_INTERVAL_SECONDS must be a number") from exc
    if not 0.1 <= poll_interval <= 300:
        raise ValueError("OUTBOX_POLL_INTERVAL_SECONDS must be between 0.1 and 300")
    batch_size = _positive_int("OUTBOX_BATCH_SIZE", 50, 1, 200)
    worker_id = os.getenv("OUTBOX_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}")

    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        LOGGER.info("Shutdown signal received; finishing current batch")
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    LOGGER.info("Starting outbox worker %s with %d handler(s)", worker_id, len(handlers))
    run_worker_loop(
        get_session_factory(),
        worker_id=worker_id,
        handlers=handlers,
        stop_event=stop_event,
        poll_interval_seconds=poll_interval,
        batch_size=batch_size,
    )


if __name__ == "__main__":
    main()
