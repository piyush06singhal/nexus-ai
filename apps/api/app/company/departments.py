"""AI Company Layer — department service.

CRUD + nested hierarchy (parent_department_id) + lifecycle for departments.
Departments belong to a company and are the unit of organizational work below
it. Budgets are scoped to departments via the shared ``budgets`` table.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger
from app.company.lifecycle import (
    CompanyLifecycleError,
    validate_department_transition,
)
from app.db.models.company import (
    Department,
    DepartmentStatus,
)
from app.db.models.employee import AIEmployee
from app.db.models.task import Task


class DepartmentManager:
    """Create, manage, and query departments."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)

    # ── CRUD ───────────────────────────────────────────────────────────

    def create(
        self,
        *,
        company_id: UUID,
        name: str,
        description: str | None = None,
        mission: str | None = None,
        manager_id: UUID | None = None,
        parent_department_id: UUID | None = None,
    ) -> Department:
        """Create a department, optionally nested under a parent."""
        if parent_department_id is not None:
            parent = self._db.get(Department, parent_department_id)
            if parent is None or parent.company_id != company_id:
                raise ValueError("Parent department not found or belongs to another company")
        dept = Department(
            company_id=company_id,
            name=name,
            description=description,
            mission=mission,
            manager_id=manager_id,
            parent_department_id=parent_department_id,
            status=DepartmentStatus.DRAFT,
        )
        self._db.add(dept)
        self._db.flush()
        self.events.log(
            actor="system",
            action="department_created",
            company_id=company_id,
            target_type="department",
            target_id=dept.id,
            details={
                "name": name,
                "parent_department_id": (
                    str(parent_department_id) if parent_department_id else None
                ),
            },
            outcome="success",
        )
        self._db.commit()
        return dept

    def get(self, department_id: UUID) -> Department | None:
        return self._db.get(Department, department_id)

    def _require(self, department_id: UUID) -> Department:
        dept = self._db.get(Department, department_id)
        if dept is None:
            raise ValueError(f"Department {department_id} not found")
        return dept

    def list_(self, company_id: UUID) -> list[Department]:
        stmt = (
            select(Department).where(Department.company_id == company_id).order_by(Department.name)
        )
        return list(self._db.execute(stmt).scalars().all())

    def update(self, department_id: UUID, **fields: Any) -> Department:
        """Partially update a department (archived departments are read-only)."""
        dept = self._require(department_id)
        if dept.status == DepartmentStatus.ARCHIVED:
            raise CompanyLifecycleError(dept.status.value, "update", entity="department")
        for key, value in fields.items():
            if key == "parent_department_id":
                if value is not None:
                    parent = self._db.get(Department, value)
                    if parent is None or parent.company_id != dept.company_id:
                        raise ValueError(
                            "Parent department not found or belongs to another company"
                        )
                setattr(dept, key, value)
            elif hasattr(dept, key) and value is not None:
                setattr(dept, key, value)
        self._db.commit()
        return dept

    def children(self, department_id: UUID) -> list[Department]:
        """Return immediate child departments."""
        stmt = (
            select(Department)
            .where(Department.parent_department_id == department_id)
            .order_by(Department.name)
        )
        return list(self._db.execute(stmt).scalars().all())

    def subtree_ids(self, department_id: UUID) -> list[UUID]:
        """Return this department + all descendant department ids (unbounded-safe)."""
        result: list[UUID] = [department_id]
        frontier = [department_id]
        while frontier:
            parent = frontier.pop(0)
            kids = [
                d.id
                for d in self._db.execute(
                    select(Department).where(Department.parent_department_id == parent)
                ).scalars()
            ]
            result.extend(kids)
            frontier.extend(kids)
        return result

    # ── Lifecycle ──────────────────────────────────────────────────────

    def activate(self, department_id: UUID) -> Department:
        dept = self._require(department_id)
        validate_department_transition(dept.status, DepartmentStatus.ACTIVE)
        dept.status = DepartmentStatus.ACTIVE
        self._db.flush()
        self.events.log(
            actor="system",
            action="department_activated",
            company_id=dept.company_id,
            target_type="department",
            target_id=dept.id,
            outcome="success",
        )
        self._db.commit()
        return dept

    def pause(self, department_id: UUID) -> Department:
        dept = self._require(department_id)
        validate_department_transition(dept.status, DepartmentStatus.PAUSED)
        dept.status = DepartmentStatus.PAUSED
        self._db.flush()
        self.events.log(
            actor="system",
            action="department_paused",
            company_id=dept.company_id,
            target_type="department",
            target_id=dept.id,
            outcome="success",
        )
        self._db.commit()
        return dept

    def archive(self, department_id: UUID) -> Department:
        dept = self._require(department_id)
        validate_department_transition(dept.status, DepartmentStatus.ARCHIVED)
        dept.status = DepartmentStatus.ARCHIVED
        self._db.flush()
        self.events.log(
            actor="system",
            action="department_archived",
            company_id=dept.company_id,
            target_type="department",
            target_id=dept.id,
            outcome="success",
        )
        self._db.commit()
        return dept

    # ── Aggregates ─────────────────────────────────────────────────────

    def employees(self, department_id: UUID, *, include_subtree: bool = False) -> list[AIEmployee]:
        """Return employees whose membership points at this department.

        When ``include_subtree`` is True, includes members of descendant
        departments too.
        """
        from app.db.models.company import OrganizationalMembership

        dept_ids: list[UUID] = (
            self.subtree_ids(department_id) if include_subtree else [department_id]
        )
        stmt = (
            select(AIEmployee)
            .join(OrganizationalMembership, OrganizationalMembership.employee_id == AIEmployee.id)
            .where(OrganizationalMembership.department_id.in_(dept_ids))
            .order_by(AIEmployee.name)
        )
        return list(self._db.execute(stmt).scalars().all())

    def memberships(self, department_id: UUID) -> list[Any]:
        """Return membership rows for a department (for timeline/direct lookup)."""
        from app.db.models.company import OrganizationalMembership

        stmt = select(OrganizationalMembership).where(
            OrganizationalMembership.department_id == department_id
        )
        return list(self._db.execute(stmt).scalars().all())

    def task_volume(self, department_id: UUID, *, include_subtree: bool = False) -> dict[str, int]:
        """Count queued/in_progress/completed/failed tasks owned by members' agents."""
        members = self.employees(department_id, include_subtree=include_subtree)
        agent_ids = [m.agent_id for m in members if m.agent_id is not None]
        counts = {"queued": 0, "in_progress": 0, "completed": 0, "failed": 0}
        if not agent_ids:
            return counts
        from sqlalchemy import func

        stmt = (
            select(Task.status, func.count(Task.id))
            .where(Task.assigned_agent_id.in_(agent_ids))
            .group_by(Task.status)
        )
        for status, count in self._db.execute(stmt):
            if status and status.value in counts:
                counts[status.value] = count
        return counts
