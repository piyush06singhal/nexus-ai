"""AI Employee OS — workload management.

Tracks active/queued/completed/failed tasks, capacity, and utilization.
Guards against overload. Task counts are derived from real :class:`Task`
rows owned by the employee's backing agent.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.employee import AIEmployee, EmployeeAvailability, EmployeeStatus
from app.db.models.task import Task, TaskStatus
from app.employee.lifecycle import is_available_for_tasks
from app.employee.types import WorkloadSnapshot


class WorkloadManager:
    """Tracks and manages employee workload."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_snapshot(self, employee_id: UUID) -> WorkloadSnapshot:
        """Build a point-in-time workload snapshot for an employee.

        Counts are derived from real :class:`Task` rows owned by the
        employee's backing agent (``assigned_agent_id``). An employee with no
        backing agent has no tasks, so counts are zero.
        """
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return WorkloadSnapshot(employee_id=employee_id)

        # Parse capacity from workload_config JSON
        capacity = settings.employee_default_capacity
        if emp.workload_config:
            import json

            cfg = json.loads(emp.workload_config)
            capacity = cfg.get("max_concurrent", capacity)

        # Count real tasks owned by the employee's backing agent.
        active = 0
        queued = 0
        completed = 0
        failed = 0
        if emp.agent_id is not None:
            counts = dict(
                self._db.execute(
                    select(Task.status, func.count())
                    .where(Task.assigned_agent_id == emp.agent_id)
                    .group_by(Task.status)
                ).all()
            )
            queued = counts.get(TaskStatus.QUEUED, 0)
            active = counts.get(TaskStatus.IN_PROGRESS, 0)
            completed = counts.get(TaskStatus.COMPLETED, 0)
            failed = counts.get(TaskStatus.FAILED, 0)

        available_slots = max(0, capacity - active)
        utilization = active / capacity if capacity > 0 else 0.0

        return WorkloadSnapshot(
            employee_id=employee_id,
            active_tasks=active,
            queued_tasks=queued,
            completed_tasks=completed,
            failed_tasks=failed,
            capacity=capacity,
            utilization=min(1.0, utilization),
            available_slots=available_slots,
        )

    def can_accept_task(self, employee_id: UUID) -> bool:
        """Return True if the employee has capacity for a new task."""
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return False
        if not is_available_for_tasks(emp.status):
            return False
        snap = self.get_snapshot(employee_id)
        return snap.available_slots > 0

    def get_utilization(self, employee_id: UUID) -> float:
        """Return current utilization (0.0–1.0)."""
        return self.get_snapshot(employee_id).utilization

    def get_available_employees(self) -> list[UUID]:
        """Return IDs of employees who can accept tasks."""
        stmt = select(AIEmployee.id).where(
            AIEmployee.status.in_([EmployeeStatus.ACTIVE, EmployeeStatus.BUSY]),
            AIEmployee.availability.in_(
                [
                    EmployeeAvailability.AVAILABLE,
                    EmployeeAvailability.BUSY,
                ]
            ),
        )
        return [row[0] for row in self._db.execute(stmt).all()]
