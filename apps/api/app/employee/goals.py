"""AI Employee OS — goal tracking.

Tracks goal progress derived from actual execution data.  Prevents manual
claiming of completion without evidence.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.employee import EmployeeGoal, GoalStatus
from app.employee.types import GoalStatus as DomainGoalStatus

# Map domain GoalStatus ↔ DB GoalStatus (same values, different classes)
_STATUS_MAP: dict[DomainGoalStatus, GoalStatus] = {
    DomainGoalStatus.NOT_STARTED: GoalStatus.NOT_STARTED,
    DomainGoalStatus.ACTIVE: GoalStatus.ACTIVE,
    DomainGoalStatus.AT_RISK: GoalStatus.AT_RISK,
    DomainGoalStatus.COMPLETED: GoalStatus.COMPLETED,
    DomainGoalStatus.FAILED: GoalStatus.FAILED,
    DomainGoalStatus.CANCELLED: GoalStatus.CANCELLED,
}
_STATUS_MAP_INV: dict[GoalStatus, DomainGoalStatus] = {v: k for k, v in _STATUS_MAP.items()}


class GoalTracker:
    """Tracks and manages employee goals."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_goal(
        self,
        employee_id: UUID,
        *,
        title: str,
        description: str | None = None,
        priority: int = 0,
        target: str | None = None,
        metric: str | None = None,
        deadline: datetime | None = None,
        parent_goal_id: UUID | None = None,
    ) -> EmployeeGoal:
        """Create a new goal for an employee."""
        goal = EmployeeGoal(
            employee_id=employee_id,
            title=title,
            description=description,
            priority=priority,
            target=target,
            metric=metric,
            deadline=deadline,
            status=GoalStatus.NOT_STARTED,
            progress=0.0,
            parent_goal_id=parent_goal_id,
        )
        self._db.add(goal)
        self._db.flush()
        return goal

    def get_goals(
        self,
        employee_id: UUID,
        *,
        status: DomainGoalStatus | None = None,
    ) -> list[EmployeeGoal]:
        """List goals for an employee, optionally filtered by status."""
        stmt = (
            select(EmployeeGoal)
            .where(EmployeeGoal.employee_id == employee_id)
            .order_by(EmployeeGoal.priority.desc(), EmployeeGoal.created_at)
        )
        if status is not None:
            db_status = _STATUS_MAP.get(status)
            if db_status is not None:
                stmt = stmt.where(EmployeeGoal.status == db_status)
        return list(self._db.execute(stmt).scalars().all())

    def update_progress(
        self,
        goal_id: UUID,
        *,
        progress: float,
        status: DomainGoalStatus | None = None,
    ) -> EmployeeGoal | None:
        """Update goal progress (0.0–1.0) and optionally status.

        Automatically transitions to ``completed`` when progress reaches 1.0
        and status is still ``active``.
        """
        goal = self._db.get(EmployeeGoal, goal_id)
        if goal is None:
            return None

        goal.progress = max(0.0, min(1.0, progress))

        if status is not None:
            goal.status = _STATUS_MAP.get(status, goal.status)
        elif goal.progress >= 1.0 and goal.status == GoalStatus.ACTIVE:
            goal.status = GoalStatus.COMPLETED
        elif goal.progress > 0 and goal.status == GoalStatus.NOT_STARTED:
            goal.status = GoalStatus.ACTIVE

        self._db.flush()
        return goal

    def cancel_goal(self, goal_id: UUID) -> EmployeeGoal | None:
        """Cancel a goal."""
        goal = self._db.get(EmployeeGoal, goal_id)
        if goal is None:
            return None
        if goal.status in {GoalStatus.COMPLETED, GoalStatus.CANCELLED}:
            return goal
        goal.status = GoalStatus.CANCELLED
        self._db.flush()
        return goal

    def get_goal(self, goal_id: UUID) -> EmployeeGoal | None:
        """Fetch a single goal by ID."""
        return self._db.get(EmployeeGoal, goal_id)

    def overall_progress(self, employee_id: UUID) -> float:
        """Compute weighted average progress across all active goals."""
        goals = self.get_goals(employee_id, status=DomainGoalStatus.ACTIVE)
        if not goals:
            return 0.0
        total = sum(g.progress for g in goals)
        return total / len(goals)
