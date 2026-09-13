"""Security operations endpoints (Phase 11) — events, alerts, incidents, audit."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db  # noqa: B008
from app.schemas.security import (
    AuditChainVerify,
    AuditEventPublic,
    IncidentActionPublic,
    IncidentActionRequest,
    IncidentCreate,
    IncidentDetailPublic,
    IncidentPublic,
    IncidentTransition,
    SecurityAlertPublic,
    SecurityAlertResolve,
    SecurityEventPublic,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/security", tags=["security"])


# ── Events ──────────────────────────────────────────────────────────────────


@router.get("/events", response_model=list[SecurityEventPublic], status_code=200)
async def list_events(
    category: str | None = None,
    company_id: UUID | None = None,
    limit: int = 100,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import SecurityEvent

    stmt = select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(limit)
    if category is not None:
        stmt = stmt.where(SecurityEvent.category == category)
    if company_id is not None:
        stmt = stmt.where(SecurityEvent.company_id == company_id)
    events = list(db.execute(stmt).scalars().all())
    return [SecurityEventPublic.model_validate(e) for e in events]


# ── Alerts ──────────────────────────────────────────────────────────────────


@router.get("/alerts", response_model=list[SecurityAlertPublic], status_code=200)
async def list_alerts(
    status: str | None = None,
    company_id: UUID | None = None,
    limit: int = 100,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import SecurityAlert

    stmt = select(SecurityAlert).order_by(SecurityAlert.severity.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(SecurityAlert.status == status)
    if company_id is not None:
        stmt = stmt.where(SecurityAlert.company_id == company_id)
    alerts = list(db.execute(stmt).scalars().all())
    return [SecurityAlertPublic.model_validate(a) for a in alerts]


@router.post("/alerts/{alert_id}/acknowledge", response_model=SecurityAlertPublic, status_code=200)
async def acknowledge_alert(
    alert_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.detection import SecurityAlertService

    alert = SecurityAlertService(db).acknowledge(alert_id, by=identity.id)
    db.commit()
    return SecurityAlertPublic.model_validate(alert)


@router.post("/alerts/{alert_id}/resolve", response_model=SecurityAlertPublic, status_code=200)
async def resolve_alert(
    alert_id: UUID,
    payload: SecurityAlertResolve,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.detection import SecurityAlertService

    alert = SecurityAlertService(db).resolve(alert_id, note=payload.resolution)
    db.commit()
    return SecurityAlertPublic.model_validate(alert)


# ── Incidents ───────────────────────────────────────────────────────────────


@router.get("/incidents", response_model=list[IncidentPublic], status_code=200)
async def list_incidents(
    status: str | None = None,
    company_id: UUID | None = None,
    limit: int = 100,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import Incident

    stmt = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Incident.status == status)
    if company_id is not None:
        stmt = stmt.where(Incident.company_id == company_id)
    incidents = list(db.execute(stmt).scalars().all())
    return [IncidentPublic.model_validate(i) for i in incidents]


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentDetailPublic,
    status_code=200,
)
async def get_incident(
    incident_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.core.errors import NotFoundError
    from app.db.models.security import Incident, IncidentAction, SecurityAlert

    incident = db.get(Incident, incident_id)
    if incident is None:
        raise NotFoundError("Incident not found.")
    alerts = list(
        db.execute(select(SecurityAlert).where(SecurityAlert.incident_id == incident_id)).scalars()
    )
    actions = list(
        db.execute(
            select(IncidentAction)
            .where(IncidentAction.incident_id == incident_id)
            .order_by(IncidentAction.created_at.desc())
        ).scalars()
    )
    return IncidentDetailPublic(
        **IncidentPublic.model_validate(incident).model_dump(),
        alerts=[SecurityAlertPublic.model_validate(a) for a in alerts],
        actions=[IncidentActionPublic.model_validate(a) for a in actions],
    )


@router.post("/incidents", response_model=IncidentPublic, status_code=201)
async def create_incident(
    payload: IncidentCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.detection import IncidentService

    incident = IncidentService(db).create(
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        company_id=payload.company_id,
        reported_by=identity.id,
        alert_ids=payload.alert_ids,
    )
    db.commit()
    return IncidentPublic.model_validate(incident)


@router.post(
    "/incidents/{incident_id}/transition",
    response_model=IncidentPublic,
    status_code=200,
)
async def transition_incident(
    incident_id: UUID,
    payload: IncidentTransition,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.detection import IncidentService

    incident = IncidentService(db).transition(
        incident_id, payload.to_status, note=payload.note, by=identity.id
    )
    db.commit()
    return IncidentPublic.model_validate(incident)


@router.post(
    "/incidents/{incident_id}/actions",
    response_model=IncidentActionPublic,
    status_code=201,
)
async def execute_incident_action(
    incident_id: UUID,
    payload: IncidentActionRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.detection import IncidentActionExecutor

    action = IncidentActionExecutor(incident_id, db=db).execute(
        payload.action, requested_by=identity.id, params=payload.params
    )
    db.commit()
    return IncidentActionPublic.model_validate(action)


# ── Audit chain ─────────────────────────────────────────────────────────────


@router.get("/audit", response_model=list[AuditEventPublic], status_code=200)
async def list_audit(
    company_id: UUID | None = None,
    limit: int = 100,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import AuditEvent

    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if company_id is not None:
        stmt = stmt.where(AuditEvent.company_id == company_id)
    events = list(db.execute(stmt).scalars().all())
    return [AuditEventPublic.model_validate(e) for e in events]


@router.get("/audit/verify", response_model=AuditChainVerify, status_code=200)
async def verify_audit(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.accountability import AuditService

    valid, checked, first_broken = AuditService(db).verify_chain()
    db.rollback()  # verify is read-only; never commit
    return AuditChainVerify(
        verified=valid,
        checked=checked,
        first_gap_at_seq=first_broken,
    )
