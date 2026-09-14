"""NEXUS headless worker entry point (Item 6 — worker topology).

Runs the workflow worker, workflow scheduler, and orchestration worker as a
standalone process without booting the HTTP API, for the split-container
production topology:

    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d worker

The API container then serves requests worker-free; this process owns the
queues.  Set ``WORKFLOW_WORKER_ENABLED`` / ``ORCHESTRATION_WORKER_ENABLED``
to select which consumers run, and the scheduler piggybacks on the workflow
worker flag exactly as it does in the API lifespan.

Run as ``python -m app.main_worker`` (sets up logging, starts the daemons,
and blocks on a signal-driven shutdown loop).
"""

from __future__ import annotations

import os
import signal
import sys
import time

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.workers import start_workers, stop_workers

logger = get_logger(__name__)

#: How often the idle loop wakes up to re-check for a shutdown signal.
_IDLE_POLL_SECONDS = 1.0

_shutdown_requested = False


def _handle_signal(signum: int, _frame: object) -> None:  # noqa: ARG001
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("shutdown_signal_received", extra={"signal": signum})


def _refresh_heartbeat() -> None:
    """Touch the configured heartbeat file (no-op when unset)."""
    if settings.worker_heartbeat_path:
        try:
            with open(settings.worker_heartbeat_path, "a", encoding="utf-8"):
                os.utime(settings.worker_heartbeat_path, None)
        except OSError:
            logger.debug("worker_heartbeat_write_failed")


def run() -> int:
    """Start queue consumers and block until a SIGINT/SIGTERM arrives."""
    setup_logging()
    logger.info(
        "NEXUS headless worker starting",
        extra={
            "env": settings.environment,
            "workflow_worker": settings.workflow_worker_enabled,
            "orchestration_worker": settings.orchestration_worker_enabled,
        },
    )

    handles = start_workers()
    if not handles.active:
        logger.warning(
            "no_workers_enabled",
            extra={"hint": "set WORKFLOW_WORKER_ENABLED and/or ORCHESTRATION_WORKER_ENABLED"},
        )

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not _shutdown_requested:
            _refresh_heartbeat()
            time.sleep(_IDLE_POLL_SECONDS)
    finally:
        stop_workers(handles)
        logger.info("NEXUS headless worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(run())
