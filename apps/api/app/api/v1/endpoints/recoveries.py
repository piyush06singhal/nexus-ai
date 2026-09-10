"""Recovery endpoints (Phase 6)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.recovery import RecoverRequest, RecoveryAttemptRead
from app.services.recovery_service import (
    RecoveryService,
    attempt_to_dict,
    diagnosis_to_dict,
    plan_to_dict,
)

router = APIRouter(tags=["recoveries"], prefix="/recoveries")


@router.get(
    "/attempts/{attempt_id}",
    response_model=RecoveryAttemptRead,
    summary="Get a recovery attempt",
)
def get_recovery(
    attempt_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> RecoveryAttemptRead:
    service = RecoveryService(db)
    attempt = service.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Recovery attempt not found")
    return RecoveryAttemptRead.model_validate(attempt_to_dict(attempt))


@router.get(
    "/executions/{execution_id}",
    response_model=list[RecoveryAttemptRead],
    summary="List recovery attempts for an execution",
)
def list_execution_recoveries(
    execution_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.schemas.recovery import RecoveryAttemptRead

    service = RecoveryService(db)
    attempts = service.list_attempts_for_execution(execution_id)
    return [RecoveryAttemptRead.model_validate(attempt_to_dict(a)) for a in attempts]


@router.post(
    "/executions/{execution_id}/recover",
    response_model=RecoveryAttemptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger recovery for a failed execution",
)
def recover_execution(
    execution_id: UUID,
    payload: RecoverRequest | None = None,
    db: Session = Depends(get_db),  # noqa: B008
) -> RecoveryAttemptRead:
    service = RecoveryService(db)
    if payload is None:
        payload = RecoverRequest(execution_id=execution_id)
    attempt = service.recover(
        execution_id=execution_id,
        error_text=payload.error_text,
        exception_type=payload.exception_type,
        tool_call_status=payload.tool_call_status,
        tool_call_result=payload.tool_call_result,
        original_plan=payload.original_plan,
    )
    from app.schemas.recovery import RecoveryAttemptRead

    return RecoveryAttemptRead.model_validate(attempt.to_dict())


@router.get(
    "/diagnoses/executions/{execution_id}",
    summary="Get the latest failure diagnosis for an execution",
)
def get_execution_diagnosis(
    execution_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
):
    service = RecoveryService(db)
    diag = service.diagnosis_for_execution(execution_id)
    if diag is None:
        raise HTTPException(status_code=404, detail="No diagnosis found for execution")
    return diagnosis_to_dict(diag)


@router.get(
    "/plans/executions/{execution_id}",
    summary="Get the latest recovery plan for an execution",
)
def get_execution_plan(
    execution_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
):
    service = RecoveryService(db)
    plan = service.plan_for_execution(execution_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No recovery plan found for execution")
    return plan_to_dict(plan)
