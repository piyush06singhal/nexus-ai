"""AI Company Layer — department endpoints (Phase 8)."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.company.budget import BudgetManager
from app.company.departments import DepartmentManager
from app.company.goals import GoalManager
from app.company.kpis import KPIService
from app.company.performance import PerformanceAggregator
from app.company.risks import RiskManager
from app.db.session import get_db
from app.schemas.company import DepartmentRead, DepartmentUpdate

router = APIRouter(tags=["departments"], prefix="/departments")


def _dept_or_404(db: Session, dept_id: UUID):
    mgr = DepartmentManager(db)
    dept = mgr.get(dept_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept


def _to_read(dept) -> DepartmentRead:
    return DepartmentRead(
        id=dept.id,
        company_id=dept.company_id,
        name=dept.name,
        description=dept.description,
        mission=dept.mission,
        manager_id=dept.manager_id,
        parent_department_id=dept.parent_department_id,
        status=dept.status,
        created_at=dept.created_at,
        updated_at=dept.updated_at,
    )


@router.get("/{department_id}", response_model=DepartmentRead, summary="Get a department")
def get_department(
    department_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> DepartmentRead:
    dept = _dept_or_404(db, department_id)
    return _to_read(dept)


@router.put("/{department_id}", response_model=DepartmentRead, summary="Update a department")
def update_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> DepartmentRead:
    mgr = DepartmentManager(db)
    try:
        dept = mgr.update(department_id, **payload.model_dump(exclude_unset=True))
        return _to_read(dept)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/{department_id}/children",
    response_model=list[DepartmentRead],
    summary="Child departments",
)
def department_children(
    department_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[DepartmentRead]:
    _dept_or_404(db, department_id)
    return [_to_read(d) for d in DepartmentManager(db).children(department_id)]


@router.get("/{department_id}/employees", summary="Employees in a department")
def department_employees(
    department_id: UUID,
    include_subtree: bool = False,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    _dept_or_404(db, department_id)
    mgr = DepartmentManager(db)
    emps = mgr.employees(department_id, include_subtree=include_subtree)
    return [
        {
            "id": str(e.id),
            "name": e.name,
            "display_name": e.display_name,
            "role": e.role,
            "department": e.department,
            "status": getattr(e.status, "value", e.status),
            "agent_id": str(e.agent_id) if e.agent_id else None,
        }
        for e in emps
    ]


@router.get("/{department_id}/goals", summary="Department goals")
def department_goals(
    department_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    dept = _dept_or_404(db, department_id)
    goal_svc = GoalManager(db)
    goals = goal_svc.list_for_scope(dept.company_id, "department", dept.id)
    return [goal_svc.to_dict(g) for g in goals]


@router.get("/{department_id}/kpis", summary="Department KPIs")
def department_kpis(
    department_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    dept = _dept_or_404(db, department_id)
    kpi_svc = KPIService(db)
    kpis = [
        k
        for k in kpi_svc.list_(dept.company_id)
        if k.scope_type.value == "department" and k.scope_id == dept.id
    ]
    return [kpi_svc.snapshot(k) for k in kpis]


@router.get("/{department_id}/performance", summary="Department performance aggregates")
def department_performance(
    department_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    dept = _dept_or_404(db, department_id)
    return PerformanceAggregator(db).aggregate(dept.company_id, dept.id)


@router.get("/{department_id}/risks", summary="Department risks")
def department_risks(
    department_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    dept = _dept_or_404(db, department_id)
    mgr = RiskManager(db)
    return [
        mgr.to_dict(r)
        for r in mgr.list_(dept.company_id, scope_type="department")
        if r.scope_id == dept.id
    ]


@router.get("/{department_id}/budget", summary="Department budget snapshot")
def department_budget(
    department_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    dept = _dept_or_404(db, department_id)
    snap = BudgetManager(db).snapshot(dept.company_id, scope_type="department", scope_id=dept.id)
    if snap is None:
        return {}
    data = asdict(snap)
    data["remaining"] = snap.remaining
    data["utilization_pct"] = (
        round((snap.spent / snap.monthly_limit) * 100, 2) if snap.monthly_limit else 0.0
    )
    return data


@router.get("/{department_id}/timeline", summary="Department timeline / audit log")
def department_timeline(
    department_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    from app.company.events import OrgEventLogger

    dept = _dept_or_404(db, department_id)
    return OrgEventLogger(db).timeline_for_target("department", dept.id)
