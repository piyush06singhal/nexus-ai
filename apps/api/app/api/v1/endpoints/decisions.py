"""AI Company Layer — decision endpoints (Phase 8).

Decision Center: create, list, and drive decisions through the review lifecycle
(submit / approve / reject / implement) with authorization + audit trail.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.company.decisions import DecisionManager
from app.company.lifecycle import CompanyLifecycleError
from app.db.session import get_db
from app.schemas.company import DecisionCreate, DecisionRead, DecisionReviewAction

router = APIRouter(tags=["decisions"], prefix="/decisions")


def _to_read(mgr: DecisionManager, decision) -> dict:
    return mgr.to_dict(decision)


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, CompanyLifecycleError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("", status_code=201, summary="Create a decision request")
def create_decision(
    payload: DecisionCreate,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    try:
        mgr = DecisionManager(db)
        decision = mgr.create(
            company_id=company_id,
            question=payload.question,
            options=payload.options,
            requester_id=payload.requester_id,
            context=payload.context,
            evidence=payload.evidence,
            rationale=payload.rationale,
            risk_level=payload.risk_level,
            risk=payload.risk,
            budget_impact=payload.budget_impact,
            required_authority=payload.required_authority,
        )
        return _to_read(mgr, decision)
    except Exception as e:
        raise _handle(e) from e


@router.get("/{decision_id}", response_model=DecisionRead, summary="Get a decision")
def get_decision(decision_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    mgr = DecisionManager(db)
    decision = mgr.get(decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return _to_read(mgr, decision)


@router.get("/{decision_id}/reviews", summary="Decision review / audit history")
def decision_reviews(
    decision_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    mgr = DecisionManager(db)
    decision = mgr.get(decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return [
        {
            "id": str(r.id),
            "decision_id": str(r.decision_id),
            "reviewer_id": str(r.reviewer_id) if r.reviewer_id else None,
            "action": r.action,
            "verdict": getattr(r.verdict, "value", r.verdict),
            "rationale": r.rationale,
            "previous_status": r.previous_status,
            "next_status": r.next_status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in mgr.reviews(decision_id)
    ]


@router.post("/{decision_id}/submit", response_model=DecisionRead, summary="Submit for review")
def submit_decision(
    decision_id: UUID,
    actor_id: UUID | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    mgr = DecisionManager(db)
    try:
        return _to_read(mgr, mgr.submit(decision_id, actor_id=actor_id))
    except Exception as e:
        raise _handle(e) from e


@router.post("/{decision_id}/approve", response_model=DecisionRead, summary="Approve a decision")
def approve_decision(
    decision_id: UUID,
    payload: DecisionReviewAction,
    reviewer_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    mgr = DecisionManager(db)
    try:
        return _to_read(
            mgr,
            mgr.approve(decision_id, reviewer_id=reviewer_id, rationale=payload.rationale),
        )
    except Exception as e:
        raise _handle(e) from e


@router.post("/{decision_id}/reject", response_model=DecisionRead, summary="Reject a decision")
def reject_decision(
    decision_id: UUID,
    payload: DecisionReviewAction,
    reviewer_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    mgr = DecisionManager(db)
    try:
        return _to_read(
            mgr,
            mgr.reject(decision_id, reviewer_id=reviewer_id, rationale=payload.rationale),
        )
    except Exception as e:
        raise _handle(e) from e


@router.post(
    "/{decision_id}/implement",
    response_model=DecisionRead,
    summary="Implement a decision",
)
def implement_decision(
    decision_id: UUID,
    actor_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    mgr = DecisionManager(db)
    try:
        return _to_read(mgr, mgr.implement(decision_id, actor_id=actor_id))
    except Exception as e:
        raise _handle(e) from e
