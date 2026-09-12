"""Computer-use session endpoints (Phase 10 §51).

Bounded simulated computer sessions. Input actions are validated by the
input controller; observations carry the ``EXTERNAL_UNTRUSTED_CONTENT`` marker
and never expose sensitive desktop content. Purchase-sensitive actions
(§67) require an approval gate before the driver performs them.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.session import get_db
from app.external.computer.session import (
    ComputerSessionLimitError,
    ComputerSessionManager,
    SensitiveComputerActionBlocked,
)
from app.external.result import ExternalActionError
from app.external.types import ExternalValidationFailure
from app.schemas.external import (
    ComputerActionCreate,
    ComputerActionRead,
    ComputerObservationRead,
    ComputerSessionCreate,
    ComputerSessionRead,
)

router = APIRouter(tags=["external-computer"], prefix="/computer/sessions")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


def _session_to_read(session: Any) -> ComputerSessionRead:
    return ComputerSessionRead(
        id=session.id,
        company_id=session.company_id,
        employee_id=session.employee_id,
        agent_id=session.agent_id,
        workflow_execution_id=session.workflow_execution_id,
        orchestration_id=session.orchestration_id,
        status=session.status.value if session.status else None,
        screen=_loads(session.screen),
        cursor=_loads(session.cursor),
        policy=_loads(session.policy),
        action_count=session.action_count,
        started_at=session.started_at,
        last_activity_at=session.last_activity_at,
        terminated_at=session.terminated_at,
        created_at=session.created_at,
    )


def _action_to_read(action: Any) -> ComputerActionRead:
    return ComputerActionRead(
        id=action.id,
        session_id=action.session_id,
        company_id=action.company_id,
        action_type=action.action_type,
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
    response_model=ComputerSessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a bounded computer-use session",
)
def create_session(
    company_id: UUID,
    payload: ComputerSessionCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ComputerSessionRead:
    _company_or_404(db, company_id)
    try:
        session = ComputerSessionManager(db).create(
            company_id=company_id,
            employee_id=payload.employee_id,
            agent_id=payload.agent_id,
        )
        return _session_to_read(session)
    except ComputerSessionLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ExternalValidationFailure as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/{company_id}",
    response_model=list[ComputerSessionRead],
    summary="List computer sessions for a company",
)
def list_sessions(company_id: UUID, db: Session = Depends(get_db)) -> list[ComputerSessionRead]:  # noqa: B008
    _company_or_404(db, company_id)
    return [_session_to_read(s) for s in ComputerSessionManager(db).list_(company_id)]


@router.get(
    "/{company_id}/{session_id}",
    response_model=ComputerSessionRead,
    summary="Get one computer session",
)
def get_session(
    company_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ComputerSessionRead:
    _company_or_404(db, company_id)
    try:
        return _session_to_read(ComputerSessionManager(db).get(company_id, session_id))
    except ExternalValidationFailure as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{company_id}/{session_id}/actions",
    response_model=ComputerActionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run one computer-input action within a session",
)
def run_action(
    company_id: UUID,
    session_id: UUID,
    payload: ComputerActionCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ComputerActionRead:
    _company_or_404(db, company_id)
    manager = ComputerSessionManager(db)
    try:
        action = manager.action(
            company_id,
            session_id,
            action_type=payload.action_type.value
            if hasattr(payload.action_type, "value")
            else str(payload.action_type),
            input_data=payload.input,
            approved_gate_id=payload.approved_gate_id,
        )
        return _action_to_read(action)
    except SensitiveComputerActionBlocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ExternalValidationFailure as exc:
        # Cross-company isolation: session not found for this company
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ComputerSessionLimitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExternalActionError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.post(
    "/{company_id}/{session_id}/pause",
    response_model=ComputerSessionRead,
    summary="Pause a computer session",
)
def pause_session(
    company_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ComputerSessionRead:
    _company_or_404(db, company_id)
    try:
        return _session_to_read(ComputerSessionManager(db).pause(company_id, session_id))
    except ExternalActionError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.post(
    "/{company_id}/{session_id}/terminate",
    response_model=ComputerSessionRead,
    summary="Terminate a computer session",
)
def terminate_session(
    company_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ComputerSessionRead:
    _company_or_404(db, company_id)
    try:
        return _session_to_read(ComputerSessionManager(db).terminate(company_id, session_id))
    except ExternalActionError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.get(
    "/{company_id}/{session_id}/observations",
    response_model=list[ComputerObservationRead],
    summary="List structured screen observations",
)
def list_observations(
    company_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ComputerObservationRead]:
    _company_or_404(db, company_id)
    try:
        rows = ComputerSessionManager(db).observations(company_id, session_id)
    except ExternalActionError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    out = []
    for row in rows:
        out.append(
            ComputerObservationRead(
                id=row.id,
                session_id=row.session_id,
                company_id=row.company_id,
                observation_number=row.observation_number,
                snapshot=_loads(row.snapshot),
                screenshot_ref=row.screenshot_ref,
                content_type=row.content_type,
                created_at=row.created_at,
            )
        )
    return out
