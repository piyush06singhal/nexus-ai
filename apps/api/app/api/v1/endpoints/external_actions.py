"""External action journal endpoints (Phase 10 §52 timeline).

``POST /{company_id}`` creates an action and drives it through the full
governance funnel (risk → policy → autonomy → approval → execute → verify →
recover → audit). High/critical or approval-required capabilities park as
``awaiting_approval`` with an ``approval_gate_id``; the operator approves via
the Phase 9 approval-gate endpoints, then replays with ``approved_gate_id``.
The ``{id}`` view includes the recovery attempt trace.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.models.external import ExternalAction
from app.db.session import get_db
from app.external.action import ExternalActionManager
from app.external.integration import IntegrationNotFoundError
from app.external.result import ExternalActionError
from app.schemas.external import (
    ExternalActionAttemptRead,
    ExternalActionCreate,
    ExternalActionRead,
)

router = APIRouter(tags=["external-actions"], prefix="/external-actions")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


def action_to_read(action: ExternalAction, attempts: list[Any] | None = None) -> ExternalActionRead:
    """Serialize the immutable journal row, parsing JSON columns."""
    return ExternalActionRead(
        id=action.id,
        company_id=action.company_id,
        integration_id=action.integration_id,
        connection_id=action.connection_id,
        employee_id=action.employee_id,
        agent_id=action.agent_id,
        execution_id=action.execution_id,
        workflow_execution_id=action.workflow_execution_id,
        orchestration_id=action.orchestration_id,
        capability=action.capability,
        action_type=action.action_type,
        input=_loads(action.input),
        risk_level=action.risk_level,
        reversibility=action.reversibility,
        idempotency_key=action.idempotency_key,
        external_operation_id=action.external_operation_id,
        policy_result=_loads(action.policy_result),
        approval_status=action.approval_status.value if action.approval_status else None,
        approval_gate_id=action.approval_gate_id,
        status=action.status,
        started_at=action.started_at,
        completed_at=action.completed_at,
        result=_loads(action.result),
        error=action.error,
        verification=_loads(action.verification),
        recovery=_loads(action.recovery),
        correlation_id=action.correlation_id,
        created_at=action.created_at,
        updated_at=action.updated_at,
        attempts=[
            ExternalActionAttemptRead(
                id=a.id,
                action_id=a.action_id,
                attempt_number=a.attempt_number,
                strategy=a.strategy,
                status=a.status,
                retryable=a.retryable,
                error_category=a.error_category,
                error=a.error,
                request_id=a.request_id,
                external_operation_id=a.external_operation_id,
                duration_ms=a.duration_ms,
                created_at=a.created_at,
            )
            for a in (attempts or [])
        ],
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
    response_model=ExternalActionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create and run an external action through the governance funnel",
)
def create_action(
    company_id: UUID,
    payload: ExternalActionCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ExternalActionRead:
    _company_or_404(db, company_id)
    mgr = ExternalActionManager(db)
    try:
        action = mgr.create(
            company_id=company_id,
            integration_id=payload.integration_id,
            capability=payload.capability,
            payload=payload.payload,
            action_type=payload.action_type,
            idempotency_key=payload.idempotency_key,
            connection_id=payload.connection_id,
            employee_id=payload.employee_id,
            agent_id=payload.agent_id,
            approved_gate_id=payload.approved_gate_id,
            correlation_id=payload.correlation_id,
        )
        attempts = mgr.attempts(company_id, action.id)
        return action_to_read(action, attempts)
    except IntegrationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExternalActionError as exc:
        # Denied/duplicate → 4xx; awaiting-approval → 202 with the gate id.
        code = exc.code or ""
        if exc.status == "awaiting_approval" or code == "approval_required":
            raise HTTPException(status_code=202, detail=exc.message) from exc
        if code in {"duplicate", "gate_used"}:
            raise HTTPException(status_code=409, detail=exc.message) from exc
        if exc.status == "blocked":
            raise HTTPException(status_code=403, detail=exc.message) from exc
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except ValueError as exc:
        raise _error(exc) from exc


@router.get(
    "/{company_id}",
    response_model=list[ExternalActionRead],
    summary="List the external action journal (company-scoped)",
)
def list_actions(
    company_id: UUID,
    capability: str | None = Query(default=None),  # noqa: B008
    action_status: str | None = Query(default=None, alias="status"),  # noqa: B008
    limit: int = Query(default=100, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ExternalActionRead]:
    _company_or_404(db, company_id)
    mgr = ExternalActionManager(db)
    rows = mgr.list_(company_id, capability=capability, status=action_status, limit=limit)
    return [action_to_read(r) for r in rows]


@router.get(
    "/{company_id}/dashboard",
    summary="External-actions dashboard aggregates (§61-style dashboard view)",
)
def dashboard(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    _company_or_404(db, company_id)
    mgr = ExternalActionManager(db)
    rows = mgr.list_(company_id, limit=200)
    counts: dict[str, int] = {}
    for row in rows:
        key = row.status.value if row.status else "unknown"
        counts[key] = counts.get(key, 0) + 1
    pending_gates = [r for r in rows if r.status and r.status.value == "awaiting_approval"]
    succeeded = counts.get("succeeded", 0)
    failed = counts.get("failed", 0)
    total = len(rows)
    return {
        "company_id": str(company_id),
        "total_actions": total,
        "by_status": counts,
        "success_rate": round(succeeded / total, 4) if total else 0.0,
        "failure_rate": round(failed / total, 4) if total else 0.0,
        "pending_approvals": [
            {
                "id": str(r.id),
                "capability": r.capability,
                "gate_id": str(r.approval_gate_id) if r.approval_gate_id else None,
                "risk_level": r.risk_level.value if r.risk_level else None,
                "created_at": _iso(r.created_at),
            }
            for r in pending_gates
        ],
        "pending_approval_count": len(pending_gates),
    }


@router.get(
    "/{company_id}/{action_id}",
    response_model=ExternalActionRead,
    summary="Get one journal row plus its recovery attempt trace",
)
def get_action(
    company_id: UUID,
    action_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ExternalActionRead:
    _company_or_404(db, company_id)
    mgr = ExternalActionManager(db)
    try:
        action = mgr.get(company_id, action_id)
        attempts = mgr.attempts(company_id, action_id)
    except ExternalActionError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return action_to_read(action, attempts)


@router.post(
    "/{company_id}/{action_id}/cancel",
    response_model=ExternalActionRead,
    summary="Cancel an awaiting-approval action (marks the journal cancelled)",
)
def cancel_action(
    company_id: UUID,
    action_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ExternalActionRead:
    _company_or_404(db, company_id)
    mgr = ExternalActionManager(db)
    try:
        action = mgr.cancel(company_id, action_id)
        attempts = mgr.attempts(company_id, action_id)
        return action_to_read(action, attempts)
    except ExternalActionError as exc:
        if exc.code == "not_found":
            raise HTTPException(status_code=404, detail=exc.message) from exc
        raise HTTPException(status_code=400, detail=exc.message) from exc


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
