"""AI Company Layer — alerts endpoints (Phase 8)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.company.alerts import AlertManager
from app.db.session import get_db

router = APIRouter(tags=["alerts"], prefix="/alerts")


@router.get("/{alert_id}", response_model=dict, summary="Get an alert")
def get_alert(alert_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    mgr = AlertManager(db)
    alert = mgr.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return mgr.to_dict(alert)


@router.post("/{alert_id}/acknowledge", response_model=dict, summary="Acknowledge an alert")
def acknowledge_alert(alert_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    mgr = AlertManager(db)
    try:
        return mgr.to_dict(mgr.acknowledge(alert_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{alert_id}/resolve", response_model=dict, summary="Resolve an alert")
def resolve_alert(alert_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    mgr = AlertManager(db)
    try:
        return mgr.to_dict(mgr.resolve(alert_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
