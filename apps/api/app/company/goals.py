"""AI Company Layer — organizational goal service.

Company and department goals that cascade into employee goals and tasks.
Parent goals roll up progress from their child goals (Company Goal →
Department Goal → Employee Goal), so goal progress is derived from real
operational evidence rather than claimed manually. ``progress`` on a leaf goal
is updated by external evidence (e.g. verified results / KPI recomputation);
parents are recomputed as the mean of their children.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger
from app.db.models.company import (
    GoalScopeType,
    GoalStatusOrg,
    OrgGoal,
)
from app.db.models.employee import AIEmployee
from app.db.models.task import Task


class GoalManager:
    """Create, query, and recompute hierarchical organizational goals."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)

    def create(
        self,
        *,
        company_id: UUID,
        scope_type: GoalScopeType,
        scope_id: UUID,
        title: str,
        description: str | None = None,
        priority: int = 0,
        target: str | None = None,
        metric: str | None = None,
        deadline: datetime | None = None,
        parent_goal_id: UUID | None = None,
        owner_id: UUID | None = None,
        progress: float = 0.0,
    ) -> OrgGoal:
        """Create a company/department goal, optionally under a parent."""
        if parent_goal_id is not None:
            parent = self._db.get(OrgGoal, parent_goal_id)
            if parent is None or parent.company_id != company_id:
                raise ValueError("Parent goal not found or belongs to another company")
            if parent_goal_id == scope_id and scope_type == parent.scope_type:
                # A goal cannot be its own parent.
                raise ValueError("Goal cannot be its own parent")
        goal = OrgGoal(
            company_id=company_id,
            scope_type=scope_type,
            scope_id=scope_id,
            parent_goal_id=parent_goal_id,
            title=title,
            description=description,
            priority=priority,
            target=target,
            metric=metric,
            deadline=deadline,
            owner_id=owner_id,
            status=self._initial_status(progress),
            progress=progress,
        )
        self._db.add(goal)
        self._db.flush()
        self.events.log(
            actor="system",
            action="goal_created",
            company_id=company_id,
            target_type="goal",
            target_id=goal.id,
            details={
                "title": title,
                "scope_type": scope_type.value,
                "parent_goal_id": str(parent_goal_id) if parent_goal_id else None,
            },
            outcome="success",
        )
        # Roll the new child's progress into its parent chain.
        if parent_goal_id is not None:
            self.recompute_progress(parent_goal_id)
        self._db.commit()
        return goal

    def get(self, goal_id: UUID) -> OrgGoal | None:
        return self._db.get(OrgGoal, goal_id)

    def _require(self, goal_id: UUID) -> OrgGoal:
        goal = self._db.get(OrgGoal, goal_id)
        if goal is None:
            raise ValueError(f"Goal {goal_id} not found")
        return goal

    def update(self, goal_id: UUID, **fields: Any) -> OrgGoal:
        """Partially update a goal and roll progress into ancestors."""
        goal = self._require(goal_id)
        if "progress" in fields and fields["progress"] is not None:
            goal.progress = max(0.0, min(1.0, float(fields["progress"])))
            goal.status = self._status_for_progress(goal.progress, goal.status)
            fields.pop("progress")
        if "status" in fields and fields["status"] is not None:
            new_status = fields["status"]
            goal.status = self._coerce_status(new_status)
            fields.pop("status")
        for key, value in fields.items():
            if hasattr(goal, key) and value is not None:
                setattr(goal, key, value)
        self._db.flush()
        self.events.log(
            actor="system",
            action="goal_updated",
            company_id=goal.company_id,
            target_type="goal",
            target_id=goal.id,
            details={"title": goal.title},
            outcome="success",
        )
        if goal.parent_goal_id is not None:
            self.recompute_progress(goal.parent_goal_id)
        self._db.commit()
        return goal

    # ── Hierarchy ─────────────────────────────────────────────────────

    def children(self, goal_id: UUID) -> list[OrgGoal]:
        stmt = (
            select(OrgGoal)
            .where(OrgGoal.parent_goal_id == goal_id)
            .order_by(OrgGoal.priority.desc(), OrgGoal.created_at)
        )
        return list(self._db.execute(stmt).scalars().all())

    def children_tree(self, goal_id: UUID) -> list[dict[str, Any]]:
        """Return the immediate children as a nested tree (one level deep)."""
        nodes = []
        for child in self.children(goal_id):
            nodes.append(
                {
                    "goal": self.to_dict(child),
                    "children": [self.to_dict(g) for g in self.children(child.id)],
                }
            )
        return nodes

    def list_for_scope(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> list[OrgGoal]:
        stmt = (
            select(OrgGoal)
            .where(
                OrgGoal.company_id == company_id,
                OrgGoal.scope_type == scope_type,
                OrgGoal.scope_id == scope_id,
            )
            .order_by(OrgGoal.priority.desc(), OrgGoal.created_at)
        )
        return list(self._db.execute(stmt).scalars().all())

    def list(self, company_id: UUID) -> list[OrgGoal]:
        stmt = (
            select(OrgGoal)
            .where(OrgGoal.company_id == company_id)
            .order_by(OrgGoal.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def tree(self, company_id: UUID) -> list[dict[str, Any]]:
        """Return the full goal tree (top-level goals with nesting)."""
        all_goals = self.list(company_id)
        by_parent: dict[UUID | None, list[OrgGoal]] = {}
        for g in all_goals:
            by_parent.setdefault(g.parent_goal_id, []).append(g)
        top_level = sorted(by_parent.get(None, []), key=lambda g: (-g.priority, g.created_at or ""))

        def _build_node(goal: OrgGoal) -> dict[str, Any]:
            return {
                "goal": self.to_dict(goal),
                "children": [_build_node(c) for c in self._ordered(by_parent.get(goal.id, []))],
            }

        return [_build_node(g) for g in top_level]

    def _ordered(self, goals: list[OrgGoal]) -> list[OrgGoal]:
        return sorted(goals, key=lambda g: (-g.priority, g.created_at or ""))

    # ── Progress / evidence ───────────────────────────────────────────

    def recompute_progress(self, goal_id: UUID) -> None:
        """Roll child progress into a parent goal (recursive upward recompute)."""
        goal = self._db.get(OrgGoal, goal_id)
        if goal is None:
            return
        kids = self.children(goal_id)
        if kids:
            goal.progress = round(sum(k.progress for k in kids) / len(kids), 4)
            goal.status = self._status_for_progress(goal.progress, goal.status)
        if goal.parent_goal_id is not None:
            self.recompute_progress(goal.parent_goal_id)

    def goal_tasks(self, goal_id: UUID) -> list[Task]:
        """Return tasks linked to a goal via its owning employee/agent.

        For employee-scoped goals, resolve the employee's backing agent and
        return that agent's tasks. For department/company goals, aggregate the
        tasks of member employees.
        """
        goal = self._require(goal_id)
        from app.db.models.company import OrganizationalMembership

        agent_ids: list[UUID] = []
        if goal.scope_type == GoalScopeType.EMPLOYEE:
            emp = self._db.get(AIEmployee, goal.scope_id)
            if emp is not None and emp.agent_id is not None:
                agent_ids.append(emp.agent_id)
        elif goal.scope_type in (GoalScopeType.COMPANY, GoalScopeType.DEPARTMENT):
            scope_id = (
                goal.company_id if goal.scope_type == GoalScopeType.COMPANY else goal.scope_id
            )
            stmt = select(OrganizationalMembership).where(
                OrganizationalMembership.company_id == goal.company_id
            )
            if goal.scope_type == GoalScopeType.DEPARTMENT:
                stmt = stmt.where(OrganizationalMembership.department_id == scope_id)
            memberships = list(self._db.execute(stmt).scalars())
            emp_ids = [m.employee_id for m in memberships]
            if emp_ids:
                emps = list(
                    self._db.execute(select(AIEmployee).where(AIEmployee.id.in_(emp_ids))).scalars()
                )
                agent_ids = [e.agent_id for e in emps if e.agent_id is not None]
        if not agent_ids:
            return []
        stmt = (
            select(Task)
            .where(Task.assigned_agent_id.in_(agent_ids))
            .order_by(Task.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())

    # ── Serialization / helpers ───────────────────────────────────────

    def to_dict(self, goal: OrgGoal) -> dict[str, Any]:
        return {
            "id": str(goal.id),
            "company_id": str(goal.company_id),
            "scope_type": goal.scope_type.value,
            "scope_id": str(goal.scope_id),
            "parent_goal_id": str(goal.parent_goal_id) if goal.parent_goal_id else None,
            "title": goal.title,
            "description": goal.description,
            "priority": goal.priority,
            "target": goal.target,
            "metric": goal.metric,
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
            "status": goal.status.value,
            "progress": goal.progress,
            "owner_id": str(goal.owner_id) if goal.owner_id else None,
            "created_at": goal.created_at.isoformat() if goal.created_at else None,
            "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
        }

    def _initial_status(self, progress: float) -> GoalStatusOrg:
        return self._status_for_progress(progress, GoalStatusOrg.NOT_STARTED)

    def _status_for_progress(self, progress: float, current: GoalStatusOrg) -> GoalStatusOrg:
        if current in (GoalStatusOrg.COMPLETED, GoalStatusOrg.FAILED, GoalStatusOrg.CANCELLED):
            return current
        if progress >= 1.0:
            return GoalStatusOrg.COMPLETED
        if progress > 0.0:
            return GoalStatusOrg.ACTIVE
        return GoalStatusOrg.NOT_STARTED

    def _coerce_status(self, value: str | GoalStatusOrg) -> GoalStatusOrg:
        if isinstance(value, GoalStatusOrg):
            return value
        return GoalStatusOrg(value)
