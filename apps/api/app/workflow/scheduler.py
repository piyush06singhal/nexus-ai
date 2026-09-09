"""Workflow trigger scheduler.

A daemon thread that polls ``workflow_triggers`` for enabled triggers on
``active`` workflows whose ``next_run_at`` has arrived.  For each due
trigger it creates a new ``WorkflowExecution`` (status=``queued``) and
advances ``next_run_at`` to the next firing time.

Cron expressions are evaluated via the ``croniter`` library (already
declared as a project dependency).  If ``croniter`` is unavailable the
scheduler falls back to fixed-interval scheduling.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.workflow import (
    TriggerType,
    Workflow,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowStatus,
    WorkflowTrigger,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

logger = get_logger(__name__)

# Whether croniter is available.
_CRONITER_AVAILABLE = False
try:
    from croniter import croniter  # type: ignore[import-untyped]

    _CRONITER_AVAILABLE = True
except ImportError:
    croniter = None  # type: ignore[assignment,misc]


def calculate_next_run(trigger: WorkflowTrigger) -> datetime | None:
    """Compute the next ``run_at`` from a trigger's configuration.

    Supports ``schedule`` triggers with:
      - ``cron``: a cron expression (requires ``croniter``).
      - ``interval``: an integer number of seconds between runs.

    Returns ``None`` for ``event``/``webhook`` triggers (they are
    invoked externally, not by the scheduler).
    """
    if trigger.trigger_type == TriggerType.EVENT or trigger.trigger_type == TriggerType.WEBHOOK:
        return None

    config_raw = trigger.configuration
    config: dict = {}
    if config_raw:
        try:
            config = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
        except (json.JSONDecodeError, TypeError):
            pass

    now = datetime.now(UTC)

    # Cron-based schedule.
    cron_expr = config.get("cron")
    if cron_expr and _CRONITER_AVAILABLE:
        try:
            cron = croniter(cron_expr, now)
            return cron.get_next(datetime)
        except (ValueError, KeyError):
            logger.warning(
                "scheduler_invalid_cron",
                extra={"cron": cron_expr, "trigger_id": str(trigger.id)},
            )

    # Fixed-interval schedule.
    interval = config.get("interval")
    if interval and isinstance(interval, (int, float)) and interval > 0:
        from datetime import timedelta

        return now + timedelta(seconds=int(interval))

    # If cron is specified but croniter unavailable, default to 30 minutes.
    if cron_expr:
        from datetime import timedelta

        logger.warning(
            "scheduler_croniter_unavailable",
            extra={"trigger_id": str(trigger.id)},
        )
        return now + timedelta(minutes=30)

    return None


class WorkflowScheduler:
    """Background daemon thread that fires due workflow triggers.

    Args:
        session_factory: A callable that returns a new ``Session`` per
            invocation (typically ``SessionLocal`` from
            ``app.db.session``).
        poll_interval: Seconds between polls.  Defaults to 30.0.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        poll_interval: float = 30.0,
    ) -> None:
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the scheduler daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="workflow-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("workflow_scheduler_started")

    def stop(self) -> None:
        """Signal the scheduler to stop and wait for the current poll cycle."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info("workflow_scheduler_stopped")

    def _run_loop(self) -> None:
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("workflow_scheduler_poll_error")
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_once(self) -> None:
        """Check for due triggers and create executions."""
        session = self._session_factory()
        try:
            now = datetime.now(UTC)
            # Find enabled triggers on active workflows that are due.
            stmt = (
                select(WorkflowTrigger, Workflow)
                .join(Workflow, WorkflowTrigger.workflow_id == Workflow.id)
                .where(WorkflowTrigger.enabled == True)  # noqa: E712
                .where(Workflow.status == WorkflowStatus.ACTIVE)
                .where(WorkflowTrigger.next_run_at <= now)
            )
            results = session.execute(stmt).all()

            for trigger, workflow in results:
                self._fire_trigger(session, trigger, workflow)
        finally:
            session.close()

    def _fire_trigger(self, session, trigger: WorkflowTrigger, workflow: Workflow) -> None:
        """Create an execution for a due trigger and advance next_run_at."""
        try:
            # Create a new execution (queued — the worker will pick it up).
            execution = WorkflowExecution(
                id=uuid4(),
                workflow_id=workflow.id,
                status=WorkflowExecutionStatus.QUEUED,
                trigger_type=trigger.trigger_type.value
                if hasattr(trigger.trigger_type, "value")
                else str(trigger.trigger_type),
            )
            session.add(execution)

            # Advance next_run_at.
            next_run = calculate_next_run(trigger)
            trigger.next_run_at = next_run

            session.commit()
            logger.info(
                "scheduler_triggered",
                extra={
                    "trigger_id": str(trigger.id),
                    "execution_id": str(execution.id),
                    "next_run_at": next_run.isoformat() if next_run else None,
                },
            )
        except Exception:
            session.rollback()
            logger.exception(
                "scheduler_trigger_failed",
                extra={"trigger_id": str(trigger.id)},
            )
