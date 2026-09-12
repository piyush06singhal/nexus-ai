"""Autonomous Startup Engine — startup plan endpoints.

Create/validate/approve a startup plan, bootstrap its company from an approved
plan, and execute an operating cycle over the plan's mission/company.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models.startup import StartupPlan
from app.db.session import get_db
from app.schemas.startup import (
    CycleRead,
    StartupPlanCreate,
    StartupPlanRead,
    StartupPlanUpdate,
    ValidationResultRead,
)
from app.startup.bootstrap import CompanyBootstrapper
from app.startup.cycle import OperatingEngine
from app.startup.mission import MissionManager
from app.startup.plans import StartupPlanManager

router = APIRouter(tags=["startup-plans"], prefix="/startup-plans")


def _plan_or_404(db: Session, company_id: UUID, mission_id: UUID, plan_id: UUID) -> StartupPlan:
    # Cross-company isolation: the mission (and therefore its plans) must
    # belong to the presented company, or the plan is indistinguishable from
    # one that does not exist.
    if MissionManager(db).get(company_id, mission_id) is None:
        raise HTTPException(status_code=404, detail="Startup plan not found")
    plan = StartupPlanManager(db).get(mission_id, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Startup plan not found")
    return plan


def _mission_or_404(db: Session, company_id: UUID, mission_id: UUID) -> None:
    if MissionManager(db).get(company_id, mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


# ── CRUD ────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=StartupPlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a startup plan for a mission",
)
def create_startup_plan(
    payload: StartupPlanCreate,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> StartupPlanRead:
    _mission_or_404(db, company_id, payload.mission_id)
    mgr = StartupPlanManager(db)
    try:
        plan = mgr.create(
            mission_id=payload.mission_id,
            strategic_plan_id=payload.strategic_plan_id,
            **payload.model_dump(exclude={"mission_id", "strategic_plan_id"}),
        )
        return mgr.to_dict(plan)
    except ValueError as e:
        raise _error(e) from e


@router.get("", response_model=list[StartupPlanRead], summary="List plans for a mission")
def list_startup_plans(
    company_id: UUID = Query(...),  # noqa: B008
    mission_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[StartupPlanRead]:
    _mission_or_404(db, company_id, mission_id)
    mgr = StartupPlanManager(db)
    return [mgr.to_dict(p) for p in mgr.list_(mission_id)]


@router.get("/{plan_id}", response_model=StartupPlanRead, summary="Get a startup plan")
def get_startup_plan(
    plan_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    mission_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> StartupPlanRead:
    plan = _plan_or_404(db, company_id, mission_id, plan_id)
    return StartupPlanManager(db).to_dict(plan)


@router.put("/{plan_id}", response_model=StartupPlanRead, summary="Update a startup plan")
def update_startup_plan(
    plan_id: UUID,
    payload: StartupPlanUpdate,
    company_id: UUID = Query(...),  # noqa: B008
    mission_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> StartupPlanRead:
    _plan_or_404(db, company_id, mission_id, plan_id)
    mgr = StartupPlanManager(db)
    try:
        plan = mgr.update(mission_id, plan_id, **payload.model_dump(exclude_unset=True))
        return mgr.to_dict(plan)
    except ValueError as e:
        raise _error(e) from e


# ── Validate / approve / bootstrap / execute ─────────────────────────────


@router.post(
    "/{plan_id}/validate",
    response_model=ValidationResultRead,
    summary="Validate a startup plan",
)
def validate_startup_plan(
    plan_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    mission_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ValidationResultRead:
    plan = _plan_or_404(db, company_id, mission_id, plan_id)
    try:
        return StartupPlanManager(db).validate(plan).to_dict()
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{plan_id}/approve",
    response_model=StartupPlanRead,
    summary="Approve a draft startup plan (records an audit trail)",
)
def approve_startup_plan(
    plan_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    mission_id: UUID = Query(...),  # noqa: B008
    approved_gate_id: UUID | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> StartupPlanRead:
    mgr = StartupPlanManager(db)
    try:
        plan = mgr.approve(
            _plan_or_404(db, company_id, mission_id, plan_id),
            actor="api",
            approved_gate_id=approved_gate_id,
        )
        return mgr.to_dict(plan)
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{plan_id}/bootstrap",
    summary="Bootstrap the mission's company from an approved plan",
)
def bootstrap_company(
    plan_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    mission_id: UUID = Query(...),  # noqa: B008
    approved_gate_id: UUID | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    plan = _plan_or_404(db, company_id, mission_id, plan_id)
    bootstrapper = CompanyBootstrapper(db)
    try:
        return bootstrapper.bootstrap(plan, approved_gate_id=approved_gate_id, actor="api")
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{plan_id}/execute",
    response_model=CycleRead,
    summary="Run an operating cycle for the plan's mission/company",
)
def execute_startup_plan(
    plan_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    mission_id: UUID = Query(...),  # noqa: B008
    approved_gate_id: UUID | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> CycleRead:
    plan = _plan_or_404(db, company_id, mission_id, plan_id)
    mission = MissionManager(db).get(plan.mission.company_id, plan.mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    try:
        return OperatingEngine(db).run_cycle(
            company_id=plan.mission.company_id,
            mission_id=plan.mission_id,
            startup_plan_id=plan.id,
            actor="api",
            approved_gate_id=approved_gate_id,
        )
    except Exception as e:  # noqa: BLE001 - surface engine errors as 400
        raise _error(e) from e
