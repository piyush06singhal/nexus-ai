"""Escalation endpoints (Phase 6, spec §41)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.recovery.escalation import escalation_to_dict
from app.schemas.recovery import EscalationDecision, EscalationListResponse, EscalationRead
from app.services.recovery_service import RecoveryService

router = APIRouter(tags=["escalations"], prefix="/escalations")


@router.get("", response_model=EscalationListResponse, summary="List escalations")
def list_escalations(
    state: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> EscalationListResponse:
    service = RecoveryService(db)
    escalations = service.list_escalations(state=state, limit=limit)

    return EscalationListResponse(
        escalations=[EscalationRead.model_validate(escalation_to_dict(e)) for e in escalations],
        total=len(escalations),
    )


@router.get("/{escalation_id}", response_model=EscalationRead, summary="Get an escalation")
def get_escalation(
    escalation_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> EscalationRead:
    service = RecoveryService(db)
    esc = service.get_escalation(escalation_id)
    if esc is None:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return EscalationRead.model_validate(escalation_to_dict(esc))


@router.post(
    "/{escalation_id}/approve",
    response_model=EscalationRead,
    summary="Approve an escalation",
)
def approve_escalation(
    escalation_id: UUID,
    decision: EscalationDecision | None = None,
    db: Session = Depends(get_db),  # noqa: B008
) -> EscalationRead:
    service = RecoveryService(db)
    esc = service.approve_escalation(escalation_id, decision.decision_reason if decision else None)
    if esc is None:
        raise HTTPException(status_code=404, detail="Escalation not found or already reviewed")
    return EscalationRead.model_validate(escalation_to_dict(esc))


@router.post(
    "/{escalation_id}/reject", response_model=EscalationRead, summary="Reject an escalation"
)
def reject_escalation(
    escalation_id: UUID,
    decision: EscalationDecision | None = None,
    db: Session = Depends(get_db),  # noqa: B008
) -> EscalationRead:
    service = RecoveryService(db)
    esc = service.reject_escalation(escalation_id, decision.decision_reason if decision else None)
    if esc is None:
        raise HTTPException(status_code=404, detail="Escalation not found or already reviewed")
    return EscalationRead.model_validate(escalation_to_dict(esc))
