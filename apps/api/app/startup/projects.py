"""Projects — discrete startup work units that carry objectives to completion.

:class:`ProjectManager` provides CRUD + lifecycle for :class:`StartupProject`
rows and records their traceability links (project → product, project → goal,
project → objectives) on the mission graph. Execution of a project's work
happens through :class:`ExecutionPlanner` / the operating cycle via the existing
Phase 1–8 engines — a project row is the plan, never a second executor.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.startup import MissionGraphRelation, StartupProject, StartupProjectStatus
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.graph import MissionGraphBuilder


class ProjectManager:
    """Create, list, update, and drive startup projects through their lifecycle."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    def create(
        self,
        *,
        company_id: UUID,
        name: str,
        description: str | None = None,
        objective: str | None = None,
        product_id: UUID | None = None,
        department_id: UUID | None = None,
        owner_id: UUID | None = None,
        status: str | None = None,
        priority: int = 0,
        budget: dict[str, Any] | None = None,
        milestones: list[dict[str, Any]] | None = None,
        dependencies: list[dict[str, Any]] | None = None,
        success_criteria: list[str] | None = None,
        start_date: datetime | None = None,
        deadline: datetime | None = None,
        goal_id: UUID | None = None,
    ) -> StartupProject:
        project = StartupProject(
            company_id=company_id,
            name=name,
            description=description,
            objective=objective,
            product_id=product_id,
            department_id=department_id,
            owner_id=owner_id,
            status=StartupProjectStatus(status or StartupProjectStatus.PLANNED.value),
            priority=priority,
            budget=json.dumps(budget) if budget else None,
            milestones=json.dumps(milestones) if milestones else None,
            dependencies=json.dumps(dependencies) if dependencies else None,
            success_criteria=json.dumps(success_criteria) if success_criteria else None,
            start_date=start_date,
            deadline=deadline,
        )
        self._db.add(project)
        self._db.commit()
        self._events.log(
            action=StartupEvents.PROJECT_CREATED,
            company_id=company_id,
            target_type="startup_project",
            target_id=project.id,
            details={"name": name, "status": project.status.value},
            outcome="success",
        )
        if product_id is not None:
            MissionGraphBuilder(self._db).link(
                company_id=company_id,
                source_type="startup_project",
                source_id=project.id,
                target_type="product",
                target_id=product_id,
                relation=MissionGraphRelation.DERIVED_FROM,
            )
        if goal_id is not None:
            MissionGraphBuilder(self._db).link(
                company_id=company_id,
                source_type="startup_project",
                source_id=project.id,
                target_type="goal",
                target_id=goal_id,
                relation=MissionGraphRelation.DERIVED_FROM,
            )
        return project

    def get(self, company_id: UUID, project_id: UUID) -> StartupProject | None:
        project = self._db.get(StartupProject, project_id)
        if project is None or project.company_id != company_id:
            return None
        return project

    def list_(
        self,
        company_id: UUID,
        *,
        status: str | None = None,
        product_id: UUID | None = None,
    ) -> list[StartupProject]:
        stmt = (
            select(StartupProject)
            .where(StartupProject.company_id == company_id)
            .order_by(StartupProject.priority.desc(), StartupProject.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(StartupProject.status == StartupProjectStatus(status))
        if product_id is not None:
            stmt = stmt.where(StartupProject.product_id == product_id)
        return list(self._db.execute(stmt).scalars().all())

    def update(self, company_id: UUID, project_id: UUID, **fields: Any) -> StartupProject:
        project = self._require(company_id, project_id)
        _json_keys = ("budget", "milestones", "dependencies", "success_criteria")
        for key, value in fields.items():
            if value is None or not hasattr(project, key):
                continue
            if key in _json_keys and isinstance(value, (list, dict)):
                setattr(project, key, json.dumps(value))
            elif key == "status":
                project.status = StartupProjectStatus(value)
            else:
                setattr(project, key, value)
        self._db.commit()
        return project

    # ── Lifecycle ──────────────────────────────────────────────────────

    def lifecycle(self, company_id: UUID, project_id: UUID, target: str) -> StartupProject:
        """Move a project to *target* (active/blocked/completed/cancelled)."""
        project = self._require(company_id, project_id)
        target_status = StartupProjectStatus(target)
        _validate_transition(project.status, target_status)
        project.status = target_status
        self._db.commit()
        self._events.log(
            action=StartupEvents.PROJECT_STATUS_CHANGED,
            company_id=company_id,
            target_type="startup_project",
            target_id=project.id,
            details={"from": project.status.value, "to": target_status.value},
            outcome="success",
        )
        return project

    # ── Traceability ───────────────────────────────────────────────────

    def link_goal(self, company_id: UUID, project_id: UUID, goal_id: UUID) -> None:
        project = self._require(company_id, project_id)
        MissionGraphBuilder(self._db).link(
            company_id=company_id,
            source_type="startup_project",
            source_id=project.id,
            target_type="goal",
            target_id=goal_id,
            relation=MissionGraphRelation.DERIVED_FROM,
            metadata={"objective": project.objective},
        )

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self, project: StartupProject) -> dict[str, Any]:
        return {
            "id": str(project.id),
            "company_id": str(project.company_id),
            "product_id": str(project.product_id) if project.product_id else None,
            "department_id": str(project.department_id) if project.department_id else None,
            "name": project.name,
            "description": project.description,
            "objective": project.objective,
            "owner_id": str(project.owner_id) if project.owner_id else None,
            "status": project.status.value,
            "priority": project.priority,
            "budget": _loads(project.budget),
            "milestones": _loads_list(project.milestones),
            "dependencies": _loads(project.dependencies),
            "success_criteria": _loads_list(project.success_criteria),
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "deadline": project.deadline.isoformat() if project.deadline else None,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        }

    def _require(self, company_id: UUID, project_id: UUID) -> StartupProject:
        project = self.get(company_id, project_id)
        if project is None:
            raise ValueError("Startup project not found")
        return project


# ── Transitions ───────────────────────────────────────────────────────────────


def _validate_transition(current: StartupProjectStatus, target: StartupProjectStatus) -> None:
    allowed: dict[StartupProjectStatus, set[StartupProjectStatus]] = {
        StartupProjectStatus.PLANNED: {
            StartupProjectStatus.ACTIVE,
            StartupProjectStatus.CANCELLED,
        },
        StartupProjectStatus.ACTIVE: {
            StartupProjectStatus.BLOCKED,
            StartupProjectStatus.COMPLETED,
            StartupProjectStatus.CANCELLED,
        },
        StartupProjectStatus.BLOCKED: {
            StartupProjectStatus.ACTIVE,
            StartupProjectStatus.CANCELLED,
        },
        StartupProjectStatus.COMPLETED: set(),
        StartupProjectStatus.CANCELLED: set(),
    }
    if target not in allowed.get(current, set()):
        raise ValueError(f"Invalid project transition: {current.value} → {target.value}")


def _loads(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _loads_list(raw: str | None) -> list[Any]:
    value = _loads(raw)
    return list(value) if isinstance(value, list) else []
