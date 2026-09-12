"""Autonomous Startup Engine — operating endpoints.

Operating cycles (run, list, resume-after-approval, pause, cancel), replanning
evaluation/application, observed company state, a composed "next actions" view,
and structured feedback records. Cycle rows are immutable once written; a
blocked cycle resumes through a *new* cycle whose ``approved_gate_id`` feeds the
engine's governance checks.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.session import get_db
from app.schemas.startup import (
    CompanyStateSnapshotRead,
    CycleCreate,
    CycleDecisionBody,
    CycleRead,
    FeedbackCreate,
    FeedbackRead,
    ReplanActionRead,
)
from app.startup.cycle import OperatingEngine
from app.startup.feedback import FeedbackService
from app.startup.gates import ApprovalGateManager
from app.startup.mission import MissionManager
from app.startup.observe import ObservationLayer
from app.startup.replan import ReplanningEngine

router = APIRouter(tags=["startup"], prefix="/startup")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


# ── Cycles ──────────────────────────────────────────────────────────────


@router.post(
    "/{company_id}/cycles",
    response_model=CycleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run an operating cycle for a company",
)
def run_cycle(
    company_id: UUID,
    payload: CycleCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> CycleRead:
    _company_or_404(db, company_id)
    mission = MissionManager(db).get(company_id, payload.mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    try:
        return OperatingEngine(db).run_cycle(
            company_id=company_id,
            mission_id=payload.mission_id,
            startup_plan_id=payload.startup_plan_id,
            actor="api",
            approved_gate_id=payload.approved_gate_id,
        )
    except Exception as e:  # noqa: BLE001 - engine errors surface as 400
        raise _error(e) from e


@router.get(
    "/{company_id}/cycles",
    response_model=list[CycleRead],
    summary="List operating cycles for a company",
)
def list_cycles(
    company_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[CycleRead]:
    _company_or_404(db, company_id)
    return OperatingEngine(db).list_cycles(company_id, limit=limit)


@router.get(
    "/{company_id}/cycles/{cycle_id}",
    response_model=CycleRead,
    summary="Get an operating cycle",
)
def get_cycle(
    company_id: UUID,
    cycle_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> CycleRead:
    _company_or_404(db, company_id)
    cycle = OperatingEngine(db).get_cycle(company_id, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Operating cycle not found")
    return cycle


@router.post(
    "/{company_id}/cycles/{cycle_id}/execute",
    response_model=CycleRead,
    summary="Resume a blocked cycle once its approval gate is granted",
)
def resume_cycle(
    company_id: UUID,
    cycle_id: UUID,
    payload: CycleDecisionBody,
    db: Session = Depends(get_db),  # noqa: B008
) -> CycleRead:
    _company_or_404(db, company_id)
    blocked = OperatingEngine(db).get_cycle(company_id, cycle_id)
    if blocked is None:
        raise HTTPException(status_code=404, detail="Operating cycle not found")
    if blocked["status"] not in ("blocked", "awaiting_approval"):
        raise HTTPException(
            status_code=400, detail="Only blocked/awaiting-approval cycles can be resumed"
        )
    mission_id = blocked.get("mission_id")
    if mission_id is None:
        raise HTTPException(status_code=400, detail="Cycle has no mission to resume")
    try:
        # A blocked cycle parks at an approval gate; resume by running a new
        # governed cycle that consumes the approved gate.
        from app.db.models.startup import OperatingCycle as OperatingCycleModel

        previous = db.get(OperatingCycleModel, cycle_id)
        return OperatingEngine(db).run_cycle(
            company_id=company_id,
            mission_id=UUID(mission_id),
            startup_plan_id=previous.startup_plan_id,
            actor="api",
            approved_gate_id=payload.approved_gate_id,
        )
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.post(
    "/{company_id}/cycles/{cycle_id}/cancel",
    response_model=CycleRead,
    summary="Cancel an operating cycle (marks the immutable record cancelled)",
)
def cancel_cycle(
    company_id: UUID,
    cycle_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> CycleRead:
    from app.db.models.startup import OperatingCycle, OperatingCycleStatus

    _company_or_404(db, company_id)
    cycle = db.get(OperatingCycle, cycle_id)
    if cycle is None or cycle.company_id != company_id:
        raise HTTPException(status_code=404, detail="Operating cycle not found")
    if cycle.status not in (OperatingCycleStatus.BLOCKED, OperatingCycleStatus.AWAITING_APPROVAL):
        raise HTTPException(
            status_code=400, detail="Only blocked/awaiting-approval cycles can be cancelled"
        )
    cycle.status = OperatingCycleStatus.CANCELLED
    db.commit()
    return OperatingEngine(db).get_cycle(company_id, cycle_id)


# ── Replanning ──────────────────────────────────────────────────────────


@router.post(
    "/{company_id}/cycles/{cycle_id}/approve",
    response_model=CycleRead,
    summary="Approve a pending approval gate referenced by a blocked cycle",
)
def approve_cycle_gate(
    company_id: UUID,
    cycle_id: UUID,
    payload: CycleDecisionBody,
    db: Session = Depends(get_db),  # noqa: B008
) -> CycleRead:
    _company_or_404(db, company_id)
    blocked = OperatingEngine(db).get_cycle(company_id, cycle_id)
    if blocked is None:
        raise HTTPException(status_code=404, detail="Operating cycle not found")
    approvals = blocked.get("approvals") or []
    if not approvals:
        raise HTTPException(status_code=400, detail="Cycle has no pending approvals")
    first = approvals[0]
    gate_id = first.get("gate_id")
    if not gate_id:
        raise HTTPException(status_code=400, detail="Cycle approval has no gate id")
    try:
        gate = ApprovalGateManager(db).approve(
            company_id, UUID(gate_id), approver_id=payload.approved_gate_id
        )
        del gate
        return OperatingEngine(db).get_cycle(company_id, cycle_id)
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{company_id}/replan",
    response_model=ReplanActionRead,
    summary="Evaluate replanning triggers and apply a bounded response",
)
def replan(
    company_id: UUID,
    trigger: str | None = Query(default=None),  # noqa: B008
    apply: bool = Query(default=False),  # noqa: B008
    approved_gate_id: UUID | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ReplanActionRead:
    _company_or_404(db, company_id)
    state = ObservationLayer(db).observe(company_id)
    replanner = ReplanningEngine(db)
    decision = replanner.evaluate(company_id=company_id, state=state, trigger=trigger)
    if decision.requires_approval:
        # Route through an approval gate rather than applying automatically.
        raise HTTPException(
            status_code=425,
            detail=(
                f"Replan response '{decision.response.value}' requires approval: {decision.reason}"
            ),
        )
    if apply:
        try:
            result = replanner.apply(
                company_id=company_id, decision=decision, approved_gate_id=approved_gate_id
            )
        except Exception as e:  # noqa: BLE001
            raise _error(e) from e
        return result
    return {"decision": decision.to_dict(), "applied": []}


# ── State / next actions / feedback ─────────────────────────────────────


@router.get(
    "/{company_id}/state",
    summary="Observe current company state (refreshes authoritative metrics)",
)
def company_state(
    company_id: UUID,
    persist: bool = Query(default=False),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    _company_or_404(db, company_id)
    observer = ObservationLayer(db)
    snapshot = observer.observe(company_id)
    if persist:
        persisted = observer.persist(company_id, snapshot)
        snapshot_id = str(persisted.id)
    else:
        snapshot_id = None
    data = snapshot.to_dict()
    data["id"] = snapshot_id
    data["company_id"] = str(company_id)
    return data


@router.get(
    "/{company_id}/state/history",
    response_model=list[CompanyStateSnapshotRead],
    summary="List persisted state snapshots",
)
def state_history(
    company_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[CompanyStateSnapshotRead]:
    _company_or_404(db, company_id)
    return ObservationLayer(db).list_snapshots(company_id, limit=limit)


@router.get(
    "/{company_id}/next-actions",
    summary="Compose the next-actions view (pending approvals + open signals)",
)
def next_actions(company_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    _company_or_404(db, company_id)
    engine = OperatingEngine(db)
    approvals = ApprovalGateManager(db)
    feedback = FeedbackService(db)
    latest = ObservationLayer(db).observe(company_id)
    pending = [approvals.to_dict(g) for g in approvals.pending(company_id)]
    latest_cycle = engine.list_cycles(company_id, limit=1)
    recent_feedback = feedback.list_(company_id, limit=10)
    return {
        "company_id": str(company_id),
        "state": latest.to_dict(),
        "pending_approvals": pending,
        "pending_approval_count": len(pending),
        "latest_cycle": latest_cycle[0] if latest_cycle else None,
        "recent_feedback": recent_feedback,
        "needs_attention": bool(pending),
    }


@router.get(
    "/{company_id}/feedback",
    response_model=list[FeedbackRead],
    summary="List structured feedback signals for a company",
)
def list_feedback(
    company_id: UUID,
    category: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[FeedbackRead]:
    _company_or_404(db, company_id)
    return FeedbackService(db).list_(company_id, category=category, limit=limit)


@router.post(
    "/{company_id}/feedback",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a structured feedback signal (never auto-executed)",
)
def create_feedback(
    company_id: UUID,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> FeedbackRead:
    _company_or_404(db, company_id)
    from app.startup.types import FeedbackRecord

    try:
        record = FeedbackService(db).record(
            company_id,
            FeedbackRecord(
                category=payload.category,
                observation=payload.observation,
                source=payload.source,
                impact=payload.impact,
                confidence=payload.confidence,
                recommendation=payload.recommendation,
                objective_type=payload.objective_type,
                related_goal_id=payload.related_goal_id,
                related_project_id=payload.related_project_id,
                related_product_id=payload.related_product_id,
            ),
            mission_id=payload.mission_id,
        )
        from app.startup.feedback import _feedback_to_dict

        return _feedback_to_dict(record)
    except ValueError as e:
        raise _error(e) from e
