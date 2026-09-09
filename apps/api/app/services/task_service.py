"""Task persistence service.

Thin CRUD over the :class:`Task` ORM model. Also records task lifecycle
transitions (assign, start, complete, fail) used by the runtime.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.db.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate


def _serialize_input(input_data: dict | None) -> str | None:
    if input_data is None:
        return None
    return json.dumps(input_data)


def _deserialize_input(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return None


class TaskService:
    """Create, read, assign, and transition tasks."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, payload: TaskCreate) -> Task:
        task = Task(
            title=payload.title,
            description=payload.description,
            input_data=_serialize_input(payload.input_data),
            assigned_agent_id=payload.assigned_agent_id,
        )
        self._db.add(task)
        self._db.commit()
        self._db.refresh(task)
        return task

    def get(self, task_id: UUID) -> Task:
        task = self._db.get(Task, task_id)
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        return task

    def list(self, *, status: TaskStatus | None = None) -> list[Task]:
        stmt = select(Task).order_by(Task.created_at.desc())
        if status is not None:
            stmt = stmt.where(Task.status == status)
        return list(self._db.scalars(stmt).all())

    def assign(self, task_id: UUID, agent_id: UUID) -> Task:
        """Assign a task to an agent (clears any previous assignment)."""
        task = self.get(task_id)
        if task.status == TaskStatus.COMPLETED:
            raise ValidationError("Cannot assign a completed task")
        task.assigned_agent_id = agent_id
        task.status = TaskStatus.QUEUED
        self._db.commit()
        self._db.refresh(task)
        return task

    def mark_in_progress(self, task_id: UUID) -> Task:
        task = self.get(task_id)
        task.status = TaskStatus.IN_PROGRESS
        self._db.commit()
        self._db.refresh(task)
        return task

    def mark_completed(self, task_id: UUID) -> Task:
        task = self.get(task_id)
        task.status = TaskStatus.COMPLETED
        task.executed_at = datetime.now(UTC)
        self._db.commit()
        self._db.refresh(task)
        return task

    def mark_failed(self, task_id: UUID) -> Task:
        task = self.get(task_id)
        task.status = TaskStatus.FAILED
        self._db.commit()
        self._db.refresh(task)
        return task

    def delete(self, task_id: UUID) -> None:
        task = self.get(task_id)
        self._db.delete(task)
        self._db.commit()


def to_dict(task: Task) -> dict:
    """Serialize a Task ORM instance for API responses."""
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "input_data": _deserialize_input(task.input_data),
        "status": task.status.value,
        "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "executed_at": task.executed_at,
    }
