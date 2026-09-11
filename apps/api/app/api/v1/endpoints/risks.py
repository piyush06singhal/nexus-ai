"""AI Company Layer — risks endpoints (Phase 8)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.company.risks import RiskManager
from app.db.session import get_db
from app.schemas.company import RiskUpdate

router = APIRouter(tags=["risks"], prefix="/risks")


@router.get("/{risk_id}", response_model=dict, summary="Get a risk")
def get_risk(risk_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    mgr = RiskManager(db)
    risk = mgr.get(risk_id)
    if risk is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    return mgr.to_dict(risk)


@router.put("/{risk_id}", response_model=dict, summary="Update a risk")
def update_risk(
    risk_id: UUID,
    payload: RiskUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    mgr = RiskManager(db)
    risk = mgr.get(risk_id)
    if risk is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    try:
        if payload.status is not None:
            mgr.update_status(risk_id, payload.status)
        if payload.severity is not None:
            mgr.update_severity(risk_id, payload.severity)
        if payload.mitigation is not None:
            mgr.update_mitigation(risk_id, payload.mitigation)
        return mgr.to_dict(mgr.get(risk_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
