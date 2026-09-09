"""Workflow execution queue.

Provides an atomic queue abstraction backed by Postgres — the
``workflow_executions`` table itself is the queue.  No Redis needed.

The core primitive is ``claim_next()`` which atomically picks the oldest
``queued`` row, marks it ``running``, and returns its ID.  Under Postgres
this uses ``SELECT … FOR UPDATE SKIP LOCKED``; under SQLite a plain
``SELECT … LIMIT 1`` + ``UPDATE`` is sufficient (serialised writes).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update

from app.core.logging import get_logger
from app.db.models.workflow import (
    WorkflowExecution,
    WorkflowExecutionStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)

# SELECT FOR UPDATE SKIP LOCKED — Postgres dialect.
_FOR_UPDATE_SKIP_LOCKED = (
    select(WorkflowExecution.id)
    .where(WorkflowExecution.status == WorkflowExecutionStatus.QUEUED)
    .order_by(WorkflowExecution.created_at)
    .limit(1)
    .with_for_update(skip_locked=True)
)


class WorkflowQueue:
    """Interface for workflow execution queuing."""

    def __init__(self, session: Session) -> None:
        self._db = session

    def claim_next(self) -> UUID | None:
        """Atomically claim the next ``queued`` execution.

        Returns the execution UUID, or ``None`` if nothing is queued.
        Uses ``FOR UPDATE SKIP LOCKED`` on Postgres; plain
        ``SELECT`` + ``UPDATE`` on SQLite.
        """
        engine_dialect = self._db.bind.dialect.name if self._db.bind else "sqlite"

        if engine_dialect == "postgresql":
            row = self._db.execute(_FOR_UPDATE_SKIP_LOCKED).first()
        else:
            # SQLite fallback — safe for dev/test (single-writer).
            stmt = (
                select(WorkflowExecution.id)
                .where(WorkflowExecution.status == WorkflowExecutionStatus.QUEUED)
                .order_by(WorkflowExecution.created_at)
                .limit(1)
            )
            row = self._db.execute(stmt).first()

        if row is None:
            return None

        exec_id: UUID = row[0]
        now = datetime.now(UTC)
        self._db.execute(
            update(WorkflowExecution)
            .where(WorkflowExecution.id == exec_id)
            .values(
                status=WorkflowExecutionStatus.RUNNING,
                started_at=now,
            )
        )
        self._db.commit()
        logger.info("queue_claimed", extra={"execution_id": str(exec_id)})
        return exec_id

    def mark_completed(self, execution_id: UUID) -> None:
        """Mark an execution as completed."""
        now = datetime.now(UTC)
        self._db.execute(
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution_id)
            .values(
                status=WorkflowExecutionStatus.COMPLETED,
                completed_at=now,
            )
        )
        self._db.commit()

    def mark_failed(self, execution_id: UUID, error: str) -> None:
        """Mark an execution as failed."""
        now = datetime.now(UTC)
        self._db.execute(
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution_id)
            .values(
                status=WorkflowExecutionStatus.FAILED,
                error=error,
                completed_at=now,
            )
        )
        self._db.commit()
