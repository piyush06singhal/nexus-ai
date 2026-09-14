"""Worker lifecycle management shared between the API and headless worker processes.

Refactored out of the FastAPI lifespan (Item 6 — worker topology) so a
separate headless process can run the same queue consumers without booting
the HTTP API. In the headless topology the API container runs workers-off
(front-line request serving only); ``run_production.sh`` and the base
docker-compose still run the in-process threaded topology unchanged.

This module has **no** side effects on import — ``start_workers()`` must be
called explicitly by the entrypoint that owns the daemon threads.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WorkerHandles:
    """Opaque container for started daemon-thread handles."""

    workflow: object | None = None
    scheduler: object | None = None
    orchestration: object | None = None

    @property
    def active(self) -> bool:
        return any((self.workflow, self.scheduler, self.orchestration))


def start_workers() -> WorkerHandles:
    """Start queue-consumer daemons based on the current settings flags.

    Returns a :class:`WorkerHandles` with non-None attributes for each
    daemon that was actually started.  Call :func:`stop_workers` on
    shutdown to signal each thread and join with a short timeout.
    """
    from app.core.config import settings
    from app.db.session import SessionLocal

    handles = WorkerHandles()

    if settings.workflow_worker_enabled:
        from app.workflow.scheduler import WorkflowScheduler
        from app.workflow.worker import WorkflowWorker

        handles.workflow = WorkflowWorker(
            SessionLocal,
            poll_interval=settings.workflow_worker_poll_interval,
        )
        handles.workflow.start()

        handles.scheduler = WorkflowScheduler(
            SessionLocal,
            poll_interval=settings.workflow_scheduler_poll_interval,
        )
        handles.scheduler.start()
        logger.info("workflow_workers_started")

    if settings.orchestration_worker_enabled:
        from app.orchestration.worker import OrchestrationWorker

        handles.orchestration = OrchestrationWorker(
            SessionLocal,
            poll_interval=settings.workflow_worker_poll_interval,
        )
        handles.orchestration.start()
        logger.info("orchestration_worker_started")

    return handles


def stop_workers(handles: WorkerHandles | None) -> None:
    """Signal each daemon thread to stop and join with a short timeout.

    Safe to call with ``None`` (no-op) and safe to call twice on the
    same handles (idempotent via each worker's own guard).
    """
    if handles is None:
        return

    if handles.workflow is not None:
        handles.workflow.stop()
    if handles.scheduler is not None:
        handles.scheduler.stop()
    if handles.orchestration is not None:
        handles.orchestration.stop()
    logger.info("worker_handles_stopped")
