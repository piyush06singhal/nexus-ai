"""Autonomous Startup Engine — mission endpoints.

Mission lifecycle + deterministic pipeline: create, analyze, validate, plan,
activate, pause, cancel, and a queryable mission graph. Every action is recorded
on the mission graph and the company event timeline; validation verdicts and
analysis outputs are persisted on the mission row.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models.startup import Mission
from app.db.session import get_db
from app.schemas.startup import (
    MissionAnalysisResultRead,
    MissionCreate,
    MissionGraphRead,
    MissionRead,
    MissionUpdate,
    TraceRead,
    ValidationResultRead,
)
from app.startup.graph import MissionGraphBuilder
from app.startup.mission import MissionManager

router = APIRouter(tags=["missions"], prefix="/missions")


def _mission_or_404(db: Session, company_id: UUID, mission_id: UUID) -> Mission:
    mission = MissionManager(db).get(company_id, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


# ── CRUD ────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=MissionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a startup mission",
)
def create_mission(
    payload: MissionCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> MissionRead:
    mgr = MissionManager(db)
    try:
        mission = mgr.create(**payload.model_dump())
        return mgr.to_dict(mission)
    except ValueError as e:
        raise _error(e) from e


@router.get("", response_model=list[MissionRead], summary="List missions for a company")
def list_missions(
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[MissionRead]:
    mgr = MissionManager(db)
    return [mgr.to_dict(m) for m in mgr.list_(company_id)]


@router.get("/{mission_id}", response_model=MissionRead, summary="Get a mission")
def get_mission(
    mission_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> MissionRead:
    mission = _mission_or_404(db, company_id, mission_id)
    return MissionManager(db).to_dict(mission)


@router.put("/{mission_id}", response_model=MissionRead, summary="Update a mission")
def update_mission(
    mission_id: UUID,
    payload: MissionUpdate,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> MissionRead:
    mgr = MissionManager(db)
    try:
        mission = mgr.update(company_id, mission_id, **payload.model_dump(exclude_unset=True))
        return mgr.to_dict(mission)
    except ValueError as e:
        raise _error(e) from e


# ── Pipeline ─────────────────────────────────────────────────────────────


@router.post(
    "/{mission_id}/analyze",
    response_model=MissionAnalysisResultRead,
    summary="Run mission analysis (deterministic by default)",
)
def analyze_mission(
    mission_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> MissionAnalysisResultRead:
    mission = _mission_or_404(db, company_id, mission_id)
    try:
        return MissionManager(db).analyze(mission).to_dict()
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{mission_id}/validate",
    response_model=ValidationResultRead,
    summary="Validate a mission against the completeness/safety checklist",
)
def validate_mission(
    mission_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ValidationResultRead:
    mission = _mission_or_404(db, company_id, mission_id)
    try:
        return MissionManager(db).validate(mission).to_dict()
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{mission_id}/plan",
    summary="Produce a strategic plan + derived startup plan for the mission",
)
def plan_mission(
    mission_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    mission = _mission_or_404(db, company_id, mission_id)
    try:
        return MissionManager(db).plan(mission)
    except ValueError as e:
        raise _error(e) from e


# ── Lifecycle ───────────────────────────────────────────────────────────


@router.post(
    "/{mission_id}/activate",
    response_model=MissionRead,
    summary="Activate a planned mission",
)
def activate_mission(
    mission_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> MissionRead:
    mgr = MissionManager(db)
    try:
        return mgr.to_dict(mgr.activate(company_id, mission_id))
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{mission_id}/pause",
    response_model=MissionRead,
    summary="Pause a mission",
)
def pause_mission(
    mission_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> MissionRead:
    mgr = MissionManager(db)
    try:
        return mgr.to_dict(mgr.pause(company_id, mission_id))
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{mission_id}/cancel",
    response_model=MissionRead,
    summary="Cancel a mission",
)
def cancel_mission(
    mission_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> MissionRead:
    mgr = MissionManager(db)
    try:
        return mgr.to_dict(mgr.cancel(company_id, mission_id))
    except ValueError as e:
        raise _error(e) from e


# ── Graph ───────────────────────────────────────────────────────────────


@router.get(
    "/{mission_id}/graph",
    response_model=MissionGraphRead,
    summary="Return the mission graph edges touching this mission",
)
def mission_graph(
    mission_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    relation: str | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> MissionGraphRead:
    _mission_or_404(db, company_id, mission_id)
    builder = MissionGraphBuilder(db)
    edges = builder.query(company_id, node_type="mission", node_id=mission_id)
    if relation is not None:
        from app.db.models.startup import MissionGraphRelation

        edges = [e for e in edges if e.relation == MissionGraphRelation(relation)]
    return {"edges": [builder.to_dict(e) for e in edges], "total": len(edges)}


@router.get(
    "/{mission_id}/graph/trace",
    response_model=TraceRead,
    summary="Trace why a mission node exists (walk back to the mission)",
)
def mission_trace(
    mission_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    node_type: str = "task",
    node_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> TraceRead:
    _mission_or_404(db, company_id, mission_id)
    return MissionGraphBuilder(db).trace(company_id, node_type, node_id)


@router.get(
    "/graph",
    response_model=MissionGraphRead,
    summary="Return the full mission graph for a company",
)
def company_mission_graph(
    company_id: UUID = Query(...),  # noqa: B008
    relation: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=500, ge=1, le=2000),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> MissionGraphRead:
    builder = MissionGraphBuilder(db)
    edges = builder.query(company_id, relation=relation, limit=limit)
    return {"edges": [builder.to_dict(e) for e in edges], "total": len(edges)}
