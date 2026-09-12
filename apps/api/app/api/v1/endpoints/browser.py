"""Browser-use session endpoints (Phase 10 §50).

Bounded simulated browser sessions driven by the deterministic mock driver.
Sessions carry a domain restriction (``allowed_domains``) and a
``EXTERNAL_UNTRUSTED_CONTENT`` observation marker; sensitive actions
(SUBMIT_PAYMENT and friends) require an approval gate before they run.
Observations are size-limited and never expose raw page bytes or screenshots.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.session import get_db
from app.external.browser.session import (
    BrowserSessionLimitError,
    BrowserSessionManager,
    SensitiveBrowserActionBlocked,
)
from app.external.result import ExternalActionError
from app.external.types import ExternalValidationFailure
from app.schemas.external import (
    BrowserActionCreate,
    BrowserActionRead,
    BrowserObservationRead,
    BrowserSessionCreate,
    BrowserSessionRead,
)

router = APIRouter(tags=["external-browser"], prefix="/browser/sessions")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


def _session_to_read(session: Any) -> BrowserSessionRead:
    return BrowserSessionRead(
        id=session.id,
        company_id=session.company_id,
        employee_id=session.employee_id,
        agent_id=session.agent_id,
        workflow_execution_id=session.workflow_execution_id,
        orchestration_id=session.orchestration_id,
        status=session.status.value if session.status else None,
        current_url=session.current_url,
        domain=session.domain,
        allowed_domains=_loads(session.allowed_domains),
        policy=_loads(session.policy),
        metadata=_loads(session.metadata_json),
        action_count=session.action_count,
        navigation_count=session.navigation_count,
        started_at=session.started_at,
        last_activity_at=session.last_activity_at,
        terminated_at=session.terminated_at,
        created_at=session.created_at,
    )


def _action_to_read(action: Any) -> BrowserActionRead:
    return BrowserActionRead(
        id=action.id,
        session_id=action.session_id,
        company_id=action.company_id,
        action_type=action.action_type,
        target=_loads(action.target),
        input=_loads(action.input),
        status=action.status,
        risk_level=action.risk_level,
        approval_status=action.approval_status.value if action.approval_status else None,
        result=_loads(action.result),
        error=action.error,
        duration_ms=action.duration_ms,
        verification=_loads(action.verification),
        created_at=action.created_at,
    )


def _loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return value


@router.post(
    "/{company_id}",
    response_model=BrowserSessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a bounded browser session",
)
def create_session(
    company_id: UUID,
    payload: BrowserSessionCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> BrowserSessionRead:
    _company_or_404(db, company_id)
    try:
        session = BrowserSessionManager(db).create(
            company_id=company_id,
            allowed_domains=payload.allowed_domains,
            employee_id=payload.employee_id,
            agent_id=payload.agent_id,
        )
        return _session_to_read(session)
    except BrowserSessionLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ExternalValidationFailure as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/{company_id}",
    response_model=list[BrowserSessionRead],
    summary="List browser sessions for a company",
)
def list_sessions(company_id: UUID, db: Session = Depends(get_db)) -> list[BrowserSessionRead]:  # noqa: B008
    _company_or_404(db, company_id)
    return [_session_to_read(s) for s in BrowserSessionManager(db).list_(company_id)]


@router.get(
    "/{company_id}/{session_id}",
    response_model=BrowserSessionRead,
    summary="Get one browser session",
)
def get_session(
    company_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> BrowserSessionRead:
    _company_or_404(db, company_id)
    try:
        return _session_to_read(BrowserSessionManager(db).get(company_id, session_id))
    except ExternalValidationFailure as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{company_id}/{session_id}/actions",
    response_model=BrowserActionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run one browser action within a session",
)
def run_action(
    company_id: UUID,
    session_id: UUID,
    payload: BrowserActionCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> BrowserActionRead:
    _company_or_404(db, company_id)
    manager = BrowserSessionManager(db)
    try:
        action = manager.action(
            company_id,
            session_id,
            action_type=payload.action_type.value
            if hasattr(payload.action_type, "value")
            else str(payload.action_type),
            target=payload.target,
            input_data=payload.input,
            approved_gate_id=payload.approved_gate_id,
        )
        return _action_to_read(action)
    except SensitiveBrowserActionBlocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ExternalValidationFailure as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrowserSessionLimitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExternalActionError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.post(
    "/{company_id}/{session_id}/pause",
    response_model=BrowserSessionRead,
    summary="Pause a browser session",
)
def pause_session(
    company_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> BrowserSessionRead:
    _company_or_404(db, company_id)
    try:
        return _session_to_read(BrowserSessionManager(db).pause(company_id, session_id))
    except ExternalActionError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.post(
    "/{company_id}/{session_id}/terminate",
    response_model=BrowserSessionRead,
    summary="Terminate a browser session",
)
def terminate_session(
    company_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> BrowserSessionRead:
    _company_or_404(db, company_id)
    try:
        return _session_to_read(BrowserSessionManager(db).terminate(company_id, session_id))
    except ExternalActionError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.get(
    "/{company_id}/{session_id}/observations",
    response_model=list[BrowserObservationRead],
    summary="List size-limited untrusted page observations",
)
def list_observations(
    company_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[BrowserObservationRead]:
    _company_or_404(db, company_id)
    try:
        rows = BrowserSessionManager(db).observations(company_id, session_id)
    except ExternalActionError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    out = []
    for row in rows:
        out.append(
            BrowserObservationRead(
                id=row.id,
                session_id=row.session_id,
                company_id=row.company_id,
                observation_number=row.observation_number,
                url=row.url,
                title=row.title,
                snapshot=_loads(row.snapshot),
                screenshot_ref=row.screenshot_ref,
                content_type=row.content_type,
                page_state=_loads(row.page_state),
                created_at=row.created_at,
            )
        )
    return out
