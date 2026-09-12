"""Autonomous Startup Engine — autonomy + approval-gate endpoints.

Read/update a company's autonomy policy and list/resolve approval gates.
Changing the autonomy level is ``change_autonomy`` — never automatic — so the
autonomy-policy update endpoint requires an approved gate id when the level
changes (the caller supplies it as the operator's authorization).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.session import get_db
from app.schemas.startup import (
    ApprovalDecisionBody,
    ApprovalGateRead,
    AutonomyPolicyRead,
    AutonomyPolicyUpdate,
)
from app.startup.autonomy import AutonomyService
from app.startup.gates import ApprovalGateManager

router = APIRouter(tags=["autonomy"], prefix="/autonomy")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


# ── Autonomy policy ─────────────────────────────────────────────────────


@router.get(
    "/{company_id}/policy",
    response_model=AutonomyPolicyRead,
    summary="Get a company's autonomy policy",
)
def get_autonomy_policy(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> AutonomyPolicyRead:
    _company_or_404(db, company_id)
    return AutonomyService(db).to_dict(company_id)


@router.put(
    "/{company_id}/policy",
    response_model=AutonomyPolicyRead,
    summary="Update a company's autonomy policy (level changes need a gate)",
)
def update_autonomy_policy(
    company_id: UUID,
    payload: AutonomyPolicyUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> AutonomyPolicyRead:
    _company_or_404(db, company_id)
    service = AutonomyService(db)
    try:
        # Raising/widening autonomy is a governed change: it requires an
        # approved gate id from the operator.
        if payload.autonomy_level is not None:
            service.enforce(
                "change_autonomy",
                company_id,
                actor="api",
                approved_gate_id=payload.approved_gate_id,
            )
        service.set_policy(
            company_id,
            autonomy_level=payload.autonomy_level,
            allow_matrix=payload.allow_matrix,
            max_employees=payload.max_employees,
            max_departments=payload.max_departments,
            max_budget=payload.max_budget,
            max_concurrent_work=payload.max_concurrent_work,
            max_provisioning_rate=payload.max_provisioning_rate,
            require_approval_for=payload.require_approval_for,
            actor="api",
        )
        return service.to_dict(company_id)
    except Exception as e:  # noqa: BLE001 - governance errors (approval required)
        raise _error(e) from e


# ── Approval gates ──────────────────────────────────────────────────────


@router.get(
    "/{company_id}/approval-gates",
    response_model=list[ApprovalGateRead],
    summary="List approval gates for a company",
)
def list_approval_gates(
    company_id: UUID,
    gate_status: str | None = Query(default=None, alias="status"),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ApprovalGateRead]:
    _company_or_404(db, company_id)
    manager = ApprovalGateManager(db)
    gates = manager.list_(company_id, status=gate_status)
    return [manager.to_dict(g) for g in gates]


@router.get(
    "/{company_id}/approval-gates/pending",
    response_model=list[ApprovalGateRead],
    summary="List pending (awaiting decision) approval gates",
)
def pending_approval_gates(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ApprovalGateRead]:
    _company_or_404(db, company_id)
    manager = ApprovalGateManager(db)
    return [manager.to_dict(g) for g in manager.pending(company_id)]


@router.get(
    "/{company_id}/approval-gates/{gate_id}",
    response_model=ApprovalGateRead,
    summary="Get an approval gate",
)
def get_approval_gate(
    company_id: UUID,
    gate_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ApprovalGateRead:
    gate = ApprovalGateManager(db).get(company_id, gate_id)
    if gate is None:
        raise HTTPException(status_code=404, detail="Approval gate not found")
    return ApprovalGateManager(db).to_dict(gate)


@router.post(
    "/{company_id}/approval-gates/{gate_id}/approve",
    response_model=ApprovalGateRead,
    summary="Approve a pending approval gate",
)
def approve_gate(
    company_id: UUID,
    gate_id: UUID,
    payload: ApprovalDecisionBody,
    db: Session = Depends(get_db),  # noqa: B008
) -> ApprovalGateRead:
    manager = ApprovalGateManager(db)
    if manager.get(company_id, gate_id) is None:
        raise HTTPException(status_code=404, detail="Approval gate not found")
    try:
        gate = manager.approve(company_id, gate_id, approver_id=payload.approver_id)
        return manager.to_dict(gate)
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{company_id}/approval-gates/{gate_id}/reject",
    response_model=ApprovalGateRead,
    summary="Reject a pending approval gate",
)
def reject_gate(
    company_id: UUID,
    gate_id: UUID,
    payload: ApprovalDecisionBody,
    db: Session = Depends(get_db),  # noqa: B008
) -> ApprovalGateRead:
    manager = ApprovalGateManager(db)
    if manager.get(company_id, gate_id) is None:
        raise HTTPException(status_code=404, detail="Approval gate not found")
    try:
        gate = manager.reject(
            company_id, gate_id, approver_id=payload.approver_id, rationale=payload.rationale
        )
        return manager.to_dict(gate)
    except ValueError as e:
        raise _error(e) from e
