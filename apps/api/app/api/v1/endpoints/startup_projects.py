"""Autonomous Startup Engine — startup project endpoints.

CRUD + lifecycle for startup projects (planned → active → blocked/completed).
Each project carries objectives, dependencies, milestones, and success criteria;
execution of its work happens through execution plans / the operating cycle.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.session import get_db
from app.schemas.startup import (
    ProjectCreate,
    ProjectLifecycleMove,
    ProjectRead,
    ProjectUpdate,
)
from app.startup.projects import ProjectManager

router = APIRouter(tags=["startup-projects"], prefix="/startup-projects")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


# ── CRUD ────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a startup project",
)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ProjectRead:
    _company_or_404(db, payload.company_id)
    manager = ProjectManager(db)
    try:
        kwargs = payload.model_dump()
        goal_id = kwargs.pop("goal_id", None)
        project = manager.create(**kwargs)
        if goal_id is not None:
            manager.link_goal(payload.company_id, project.id, goal_id)
        return manager.to_dict(project)
    except ValueError as e:
        raise _error(e) from e


@router.get("", response_model=list[ProjectRead], summary="List projects for a company")
def list_projects(
    company_id: UUID = Query(...),  # noqa: B008
    status_filter: str | None = Query(default=None, alias="status"),  # noqa: B008
    product_id: UUID | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ProjectRead]:
    _company_or_404(db, company_id)
    manager = ProjectManager(db)
    projects = manager.list_(company_id, status=status_filter, product_id=product_id)
    return [manager.to_dict(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectRead, summary="Get a startup project")
def get_project(
    project_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProjectRead:
    manager = ProjectManager(db)
    project = manager.get(company_id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Startup project not found")
    return manager.to_dict(project)


@router.put("/{project_id}", response_model=ProjectRead, summary="Update a startup project")
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProjectRead:
    manager = ProjectManager(db)
    try:
        project = manager.update(company_id, project_id, **payload.model_dump(exclude_unset=True))
        return manager.to_dict(project)
    except ValueError as e:
        raise _error(e) from e


# ── Lifecycle ───────────────────────────────────────────────────────────


@router.post(
    "/{project_id}/status",
    response_model=ProjectRead,
    summary="Move a project through its lifecycle",
)
def project_status(
    project_id: UUID,
    payload: ProjectLifecycleMove,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProjectRead:
    manager = ProjectManager(db)
    if manager.get(company_id, project_id) is None:
        raise HTTPException(status_code=404, detail="Startup project not found")
    try:
        project = manager.lifecycle(company_id, project_id, payload.target.value)
        return manager.to_dict(project)
    except ValueError as e:
        raise _error(e) from e
