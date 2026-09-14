"""Orchestration execution worker.

A daemon thread that pulls orchestrations off the request path when
``settings.orchestration_worker_enabled`` is true: it claims the oldest
``created`` orchestration, runs it to a terminal status via the same
:class:`~app.orchestration.orchestrator.Orchestrator` that the synchronous
``/execute`` endpoint uses, and — on startup — recovers orchestrations that a
previous process left mid-run.

It deliberately mirrors :class:`app.workflow.worker.WorkflowWorker` so the two
queue consumers share the same shape. When the flag is off (the default) the
synchronous ``/execute`` path is untouched and nothing here runs.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update

from app.core.logging import get_logger
from app.db.models.orchestration import Orchestration, OrchestrationStatus
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.policies import OrchestrationLimits

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

logger = get_logger(__name__)

# Runs active longer than this are considered stale and recovered on startup.
_STALE_THRESHOLD_SECONDS = 3600  # 1 hour

#: States that mean "an engine is (was) actively working this run".
_ACTIVE_STATES = (
    OrchestrationStatus.PLANNING,
    OrchestrationStatus.ASSIGNING,
    OrchestrationStatus.RUNNING,
    OrchestrationStatus.SYNTHESIZING,
)


class OrchestrationWorker:
    """Background daemon thread that dequeues and executes orchestrations."""

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
        """Start the worker daemon thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="orchestration-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("orchestration_worker_started")

    def stop(self) -> None:
        """Signal the worker to stop and wait for the current poll cycle."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info("orchestration_worker_stopped")

    # ── main loop ──────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        try:
            self.recover_stale()
        except Exception:
            logger.exception("orchestration_worker_recover_failed")

        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("orchestration_worker_poll_error")
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_once(self) -> None:
        """Claim and execute one orchestration (no-op when nothing is queued)."""
        session = self._session_factory()
        try:
            orch_id = self._claim_next(session)
            if orch_id is None:
                return

            orchestration = session.get(Orchestration, orch_id)
            if orchestration is None:
                return

            limits = OrchestrationLimits.from_settings(_settings())
            from sqlalchemy.orm import sessionmaker

            # Worker task sessions bind to the same engine as the control
            # session (mirrors OrchestrationService.execute).
            worker_factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
            orchestrator = Orchestrator(worker_factory, limits=limits)
            try:
                orchestrator.execute(orchestration, session)
            except Exception as exc:
                # Orchestrator.execute handles its own lifecycle errors; this
                # catches session-level failures so the row still lands
                # terminal instead of being left in an active state.
                logger.exception(
                    "orchestration_worker_execution_failed",
                    extra={"orchestration_id": str(orch_id), "error": str(exc)},
                )
                self._mark_failed(session, orch_id, f"Worker error: {exc}")
        finally:
            session.close()

    # ── queue primitives ───────────────────────────────────────────────────

    @staticmethod
    def _claim_next(session) -> UUID | None:
        """Atomically claim the oldest ``created`` orchestration.

        Mirrors :meth:`WorkflowQueue.claim_next`: the claim *transitions* the
        row to ``running`` (with ``started_at``) inside one transaction, so the
        row is no longer visible to the queue and a crash mid-run is caught by
        stale recovery instead of being re-executed. Under Postgres ``FOR
        UPDATE SKIP LOCKED`` makes the pick concurrency-safe; SQLite is
        single-writer so a plain ``SELECT`` + ``UPDATE`` suffices.
        """
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            row = session.execute(
                select(Orchestration.id)
                .where(Orchestration.status == OrchestrationStatus.CREATED)
                .order_by(Orchestration.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
        else:
            row = session.execute(
                select(Orchestration.id)
                .where(Orchestration.status == OrchestrationStatus.CREATED)
                .order_by(Orchestration.created_at)
                .limit(1)
            ).first()
        if row is None:
            return None
        orch_id = UUID(str(row[0]))
        session.execute(
            update(Orchestration)
            .where(Orchestration.id == orch_id)
            .values(status=OrchestrationStatus.RUNNING, started_at=datetime.now(UTC))
        )
        session.commit()
        logger.info("orchestration_claimed", extra={"orchestration_id": str(orch_id)})
        return orch_id

    @staticmethod
    def _mark_failed(session, orchestration_id: UUID, error: str) -> None:
        now = datetime.now(UTC)
        session.execute(
            update(Orchestration)
            .where(Orchestration.id == orchestration_id)
            .values(
                status=OrchestrationStatus.FAILED,
                error=error,
                completed_at=now,
            )
        )
        session.commit()

    def recover_stale(self) -> None:
        """Mark active runs interrupted by a crash as ``failed``.

        Mirrors the workflow worker: interrupted work is surfaced as terminal
        (never silently re-executed so no duplicate side-effects).
        """
        session = self._session_factory()
        try:
            cutoff = datetime.now(UTC) - timedelta(seconds=_STALE_THRESHOLD_SECONDS)
            stmt = select(Orchestration).where(Orchestration.status.in_(_ACTIVE_STATES))
            stale_ids: list[UUID] = []
            for orch in session.scalars(stmt):
                started = orch.started_at or orch.created_at
                if started is None:
                    continue
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                if started < cutoff:
                    stale_ids.append(orch.id)

            if stale_ids:
                now = datetime.now(UTC)
                session.execute(
                    update(Orchestration)
                    .where(Orchestration.id.in_(stale_ids))
                    .values(
                        status=OrchestrationStatus.FAILED,
                        error="Execution interrupted (recovered on startup)",
                        completed_at=now,
                    )
                )
                session.commit()
                logger.info(
                    "orchestration_worker_recovered_stale",
                    extra={"count": len(stale_ids)},
                )
        finally:
            session.close()


def _settings():
    from app.core.config import settings

    return settings
