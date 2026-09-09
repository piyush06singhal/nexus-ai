"""Workflow execution worker.

A daemon thread that polls the DB for queued workflow executions, claims
them atomically via :class:`WorkflowQueue`, and runs them through the
:class:`WorkflowEngine`.  On startup it also recovers stale "running"
executions that were interrupted by a previous crash.

The worker is started by the FastAPI lifespan when
``settings.workflow_worker_enabled`` is ``True``.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update

from app.core.logging import get_logger
from app.db.models.workflow import (
    WorkflowExecution,
    WorkflowExecutionStatus,
)
from app.workflow.engine import WorkflowEngine
from app.workflow.queue import WorkflowQueue

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

logger = get_logger(__name__)

# Executions running longer than this are considered stale and will be
# recovered as timed_out on worker startup.
_STALE_THRESHOLD_SECONDS = 3600  # 1 hour


class WorkflowWorker:
    """Background daemon thread that dequeues and runs workflow executions.

    Args:
        session_factory: A callable that returns a new ``Session`` per
            invocation (typically ``SessionLocal`` from
            ``app.db.session``).
        poll_interval: Seconds between queue polls.  Defaults to 1.0.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        poll_interval: float = 1.0,
    ) -> None:
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the worker daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="workflow-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("workflow_worker_started")

    def stop(self) -> None:
        """Signal the worker to stop and wait for the current poll cycle."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info("workflow_worker_stopped")

    def _run_loop(self) -> None:
        """Main loop: recover stale executions, then poll-claim-execute."""
        try:
            self.recover_stale()
        except Exception:
            logger.exception("workflow_worker_recover_failed")

        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("workflow_worker_poll_error")
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_once(self) -> None:
        """Claim and execute one queued workflow."""
        session = self._session_factory()
        try:
            queue = WorkflowQueue(session)
            exec_id: UUID | None = queue.claim_next()
            if exec_id is None:
                return

            engine = WorkflowEngine(session)
            try:
                engine.execute(exec_id)
            except Exception as exc:
                logger.exception(
                    "workflow_worker_execution_failed",
                    extra={"execution_id": str(exec_id), "error": str(exc)},
                )
                # The engine should have marked the execution FAILED, but if
                # it crashed before doing so, mark it manually.
                existing = session.get(WorkflowExecution, exec_id)
                if existing and existing.status == WorkflowExecutionStatus.RUNNING:
                    queue.mark_failed(exec_id, f"Worker error: {exc}")
        finally:
            session.close()

    def recover_stale(self) -> None:
        """Mark stale ``running`` executions as ``timed_out``.

        Called once on startup to handle executions that were interrupted
        by a crash/restart before they could finish.  Comparison is done in
        Python (after normalising naive datetimes) so it works across both
        SQLite and Postgres.
        """
        session = self._session_factory()
        try:
            cutoff = datetime.now(UTC) - timedelta(seconds=_STALE_THRESHOLD_SECONDS)
            stmt = select(WorkflowExecution).where(
                WorkflowExecution.status == WorkflowExecutionStatus.RUNNING
            )
            stale_ids: list[UUID] = []
            for ex in session.scalars(stmt):
                started = ex.started_at
                if started is None:
                    continue
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                if started < cutoff:
                    stale_ids.append(ex.id)

            if stale_ids:
                session.execute(
                    update(WorkflowExecution)
                    .where(WorkflowExecution.id.in_(stale_ids))
                    .values(
                        status=WorkflowExecutionStatus.TIMED_OUT,
                        error="Execution timed out (recovered on startup)",
                        completed_at=datetime.now(UTC),
                    )
                )
                session.commit()
                logger.info(
                    "workflow_worker_recovered_stale",
                    extra={"count": len(stale_ids)},
                )
        finally:
            session.close()
