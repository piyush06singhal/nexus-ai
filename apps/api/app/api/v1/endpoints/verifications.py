"""Verification endpoints (Phase 6)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.verification import (
    VerificationListResponse,
    VerificationPolicyCreate,
    VerificationPolicyRead,
    VerificationResultRead,
    VerificationRunRead,
    VerifyRequest,
)
from app.services.verification_service import (
    VerificationService,
    run_to_dict,
    to_dict,
)

router = APIRouter(tags=["verifications"], prefix="/verifications")


@router.get("", response_model=VerificationListResponse, summary="List verification runs")
def list_verifications(
    status_filter: str | None = Query(default=None, alias="status"),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VerificationListResponse:
    service = VerificationService(db)
    runs = service.list_runs(status=status_filter, limit=limit)
    return VerificationListResponse(
        runs=[VerificationRunRead.model_validate(run_to_dict(r)) for r in runs],
        total=len(runs),
    )


@router.post(
    "",
    response_model=VerificationResultRead,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger verification",
)
def create_verification(
    payload: VerifyRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> VerificationResultRead:
    service = VerificationService(db)

    if payload.execution_id and not payload.result_data:
        result = service.verify_execution(
            payload.execution_id,
            risk_level=payload.risk_level,
            policy_override=payload.policy_override,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        return VerificationResultRead.model_validate(to_dict(result))

    if payload.result_data:
        result = service.verify_data(
            payload.result_data,
            execution_id=payload.execution_id,
            risk_level=payload.risk_level,
        )
        return VerificationResultRead.model_validate(to_dict(result))

    raise HTTPException(status_code=400, detail="Provide execution_id or result_data")


@router.get(
    "/{verification_id}", response_model=VerificationResultRead, summary="Get a verification result"
)
def get_verification(
    verification_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> VerificationResultRead:
    service = VerificationService(db)
    result = service.get(verification_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Verification result not found")
    return VerificationResultRead.model_validate(to_dict(result))


# ── Policies ──────────────────────────────────────────────────────────────────


@router.post(
    "/policies", response_model=VerificationPolicyRead, summary="Create a verification policy"
)
def create_policy(
    payload: VerificationPolicyCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> VerificationPolicyRead:
    service = VerificationService(db)
    row = service.create_policy(
        name=payload.name,
        config=payload.config,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
    )
    from app.verification.service import policy_to_dict

    return VerificationPolicyRead.model_validate(policy_to_dict(row))


@router.get(
    "/policies/{policy_id}",
    response_model=VerificationPolicyRead,
    summary="Get a verification policy",
)
def get_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> VerificationPolicyRead:
    service = VerificationService(db)
    row = service.get_policy(policy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Verification policy not found")
    from app.verification.service import policy_to_dict

    return VerificationPolicyRead.model_validate(policy_to_dict(row))


# ── Runs ──────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}",
    response_model=VerificationResultRead,
    summary="Get a verification run's result",
)
def get_run(
    run_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> VerificationResultRead:
    from app.schemas.verification import VerificationRunRead

    service = VerificationService(db)
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Verification run not found")
    return VerificationRunRead.model_validate(run_to_dict(run))
