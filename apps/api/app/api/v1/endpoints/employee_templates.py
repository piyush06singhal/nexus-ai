"""AI Employee OS — template endpoints (Phase 7)."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.employee.manager import EmployeeManager
from app.schemas.employee import (
    CreateFromTemplateRequest,
    EmployeeRead,
    TemplateCreate,
    TemplateList,
    TemplateRead,
)

router = APIRouter(tags=["employee-templates"], prefix="/employee-templates")


def _tmpl_to_read(t) -> TemplateRead:
    """Convert an EmployeeTemplate ORM object to TemplateRead schema."""
    return TemplateRead(
        id=t.id,
        name=t.name,
        description=t.description,
        role=t.role,
        skills=json.loads(t.skills) if t.skills else None,
        responsibilities=json.loads(t.responsibilities) if t.responsibilities else None,
        tools=json.loads(t.tools) if t.tools else None,
        policies=json.loads(t.policies) if t.policies else None,
        verification_policy=json.loads(t.verification_policy) if t.verification_policy else None,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _emp_to_read(emp) -> EmployeeRead:
    """Convert an AIEmployee ORM object to EmployeeRead schema."""
    return EmployeeRead(
        id=emp.id,
        name=emp.name,
        display_name=emp.display_name,
        description=emp.description,
        role=emp.role,
        department=emp.department,
        status=emp.status,
        availability=emp.availability,
        agent_id=emp.agent_id,
        skills=json.loads(emp.skills) if emp.skills else None,
        responsibilities=json.loads(emp.responsibilities) if emp.responsibilities else None,
        goals=json.loads(emp.goals) if emp.goals else None,
        tools=json.loads(emp.tools) if emp.tools else None,
        permissions=json.loads(emp.permissions) if emp.permissions else None,
        memory_namespace=emp.memory_namespace,
        work_preferences=json.loads(emp.work_preferences) if emp.work_preferences else None,
        workload_config=json.loads(emp.workload_config) if emp.workload_config else None,
        performance_profile=(
            json.loads(emp.performance_profile) if emp.performance_profile else None
        ),
        policies=json.loads(emp.policies) if emp.policies else None,
        created_at=emp.created_at,
        updated_at=emp.updated_at,
    )


@router.get(
    "",
    response_model=TemplateList,
    summary="List employee templates",
)
def list_templates(
    db: Session = Depends(get_db),  # noqa: B008
) -> TemplateList:
    mgr = EmployeeManager(db)
    templates = mgr.templates.list_templates()
    return TemplateList(
        items=[_tmpl_to_read(t) for t in templates],
        total=len(templates),
    )


@router.post(
    "",
    response_model=TemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee template",
)
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> TemplateRead:
    mgr = EmployeeManager(db)
    t = mgr.templates.create_template(
        name=payload.name,
        description=payload.description,
        role=payload.role,
        skills=payload.skills,
        responsibilities=payload.responsibilities,
        tools=payload.tools,
        policies=payload.policies,
        verification_policy=payload.verification_policy,
    )
    return _tmpl_to_read(t)


@router.get(
    "/{template_id}",
    response_model=TemplateRead,
    summary="Get an employee template",
)
def get_template(
    template_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> TemplateRead:
    mgr = EmployeeManager(db)
    t = mgr.templates.get_template(template_id)
    if t is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Template not found")
    return _tmpl_to_read(t)


@router.post(
    "/{template_id}/create",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee from a template",
)
def create_from_template(
    template_id: UUID,
    payload: CreateFromTemplateRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeRead:
    mgr = EmployeeManager(db)
    emp = mgr.templates.create_employee_from_template(
        template_id,
        name=payload.name,
        display_name=payload.display_name,
        agent_id=payload.agent_id,
        overrides=payload.overrides,
    )
    if emp is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Template not found")
    return _emp_to_read(emp)
