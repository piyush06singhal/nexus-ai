"""Execution persistence service.

Creates and queries :class:`AgentExecution` records. The runtime calls this
to persist the outcome of each agent task execution, keeping DB concerns out
of the execution pipeline.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models.execution import AgentExecution, ExecutionStatus
from app.schemas.runtime import AgentResult


def _dumps(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return None


class ExecutionService:
    """Create and query agent executions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def begin(self, *, task_id: UUID, agent_id: UUID, input_data: dict | None) -> AgentExecution:
        """Persist a new in-flight execution and return it."""
        execution = AgentExecution(
            task_id=task_id,
            agent_id=agent_id,
            status=ExecutionStatus.RUNNING,
            input_data=_dumps(input_data),
        )
        self._db.add(execution)
        self._db.commit()
        self._db.refresh(execution)
        execution.started_at = datetime.now(UTC)
        self._db.commit()
        self._db.refresh(execution)
        return execution

    def complete(
        self,
        execution_id: UUID,
        *,
        result: AgentResult,
        provider: str,
        model_name: str,
        usage,
        latency_ms: float,
        estimated_cost: float,
    ) -> AgentExecution:
        execution = self._get(execution_id)
        execution.status = ExecutionStatus.SUCCEEDED
        execution.output_data = _dumps(result.model_dump())
        execution.provider = provider
        execution.model_name = model_name
        execution.completed_at = datetime.now(UTC)
        if usage is not None:
            execution.prompt_tokens = usage.prompt_tokens
            execution.completion_tokens = usage.completion_tokens
            execution.total_tokens = usage.total_tokens
        execution.estimated_cost = estimated_cost
        execution.latency_ms = latency_ms
        self._db.commit()
        self._db.refresh(execution)
        return execution

    def fail(
        self,
        execution_id: UUID,
        *,
        error: str,
        provider: str | None = None,
        model_name: str | None = None,
    ) -> AgentExecution:
        execution = self._get(execution_id)
        execution.status = ExecutionStatus.FAILED
        execution.error = error
        execution.completed_at = datetime.now(UTC)
        if provider is not None:
            execution.provider = provider
        if model_name is not None:
            execution.model_name = model_name
        self._db.commit()
        self._db.refresh(execution)
        return execution

    def get(self, execution_id: UUID) -> AgentExecution:
        return self._get(execution_id)

    def list_by_task(self, task_id: UUID) -> list[AgentExecution]:
        stmt = (
            select(AgentExecution)
            .where(AgentExecution.task_id == task_id)
            .order_by(AgentExecution.created_at.desc())
        )
        return list(self._db.scalars(stmt).all())

    def list_all(self, *, limit: int = 50) -> list[AgentExecution]:
        """Return the most recent executions across all tasks (activity feed)."""
        stmt = select(AgentExecution).order_by(AgentExecution.created_at.desc()).limit(limit)
        return list(self._db.scalars(stmt).all())

    def _get(self, execution_id: UUID) -> AgentExecution:
        execution = self._db.get(AgentExecution, execution_id)
        if execution is None:
            raise NotFoundError(f"Execution {execution_id} not found")
        return execution


def to_dict(execution: AgentExecution) -> dict:
    """Serialize an AgentExecution ORM instance for API responses."""
    return {
        "id": str(execution.id),
        "task_id": str(execution.task_id),
        "agent_id": str(execution.agent_id),
        "status": execution.status.value,
        "input_data": _loads(execution.input_data),
        "output_data": _loads(execution.output_data),
        "error": execution.error,
        "provider": execution.provider,
        "model_name": execution.model_name,
        "prompt_tokens": execution.prompt_tokens,
        "completion_tokens": execution.completion_tokens,
        "total_tokens": execution.total_tokens,
        "estimated_cost": execution.estimated_cost,
        "latency_ms": execution.latency_ms,
        "created_at": execution.created_at,
        "started_at": execution.started_at,
        "completed_at": execution.completed_at,
    }
