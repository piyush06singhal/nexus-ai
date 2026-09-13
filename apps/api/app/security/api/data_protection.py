"""Data-protection endpoints (Phase 11) — classification, transfer policy, retention."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.security import DataClassificationRecord, RetentionPolicy
from app.db.session import get_db  # noqa: B008
from app.schemas.security import (
    DataClassificationPublic,
    DataClassificationSetRequest,
    RetentionPolicyPublic,
    RetentionPolicySetRequest,
    TransferCheckRequest,
    TransferDecisionPublic,
)
from app.security.api.deps import get_current_identity
from app.security.data_protection import (
    DataClassificationService,
    DataTransferPolicy,
    RetentionService,
)

router = APIRouter(prefix="/data", tags=["data-protection"])


# ── Classification registry ─────────────────────────────────────────────────


@router.get("/classifications", response_model=list[DataClassificationPublic], status_code=200)
async def list_classifications(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rows = list(db.execute(select(DataClassificationRecord)).scalars().all())
    return [
        DataClassificationPublic(
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            classification=r.classification,
            sensitivity_reason=r.sensitivity_reason,
        )
        for r in rows
    ]


@router.post(
    "/classifications",
    response_model=DataClassificationPublic,
    status_code=201,
)
async def set_classification(
    payload: DataClassificationSetRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    svc = DataClassificationService(db)
    row = svc.classify(
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        classification=payload.classification,
        sensitivity_reason=payload.sensitivity_reason,
        created_by=identity.id,
    )
    db.commit()
    return DataClassificationPublic(
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        classification=row.classification,
        sensitivity_reason=row.sensitivity_reason,
    )


# ── Transfer policy check ───────────────────────────────────────────────────


@router.post("/transfer-check", response_model=TransferDecisionPublic, status_code=200)
async def check_transfer(
    payload: TransferCheckRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.data_protection import DEFAULT_MAX_OUTBOUND

    decision = DataTransferPolicy(db).evaluate_transfer(
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        payload=payload.payload or {},
        destination=payload.destination,
        actor_id=identity.id,
        max_outbound=payload.max_outbound or DEFAULT_MAX_OUTBOUND,
    )
    db.commit()
    return TransferDecisionPublic(
        allowed=decision.allowed,
        reason=decision.reason,
        target_classification=decision.target_classification,
        destination=decision.destination,
        requires_approval=decision.requires_approval,
        blocked_fields=decision.blocked_fields,
    )


# ── Retention policies ──────────────────────────────────────────────────────


@router.get("/retention", response_model=list[RetentionPolicyPublic], status_code=200)
async def list_retention(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rows = list(db.execute(select(RetentionPolicy)).scalars().all())
    return [RetentionPolicyPublic.model_validate(r) for r in rows]


@router.post("/retention", response_model=RetentionPolicyPublic, status_code=201)
async def set_retention(
    payload: RetentionPolicySetRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    policy = RetentionService(db).set_policy(
        entity_type=payload.entity_type,
        retention_days=payload.retention_days,
        deletion_semantics=payload.deletion_semantics,
        retention_lock=payload.retention_lock,
        changed_by=identity.id,
    )
    db.commit()
    return RetentionPolicyPublic.model_validate(policy)
