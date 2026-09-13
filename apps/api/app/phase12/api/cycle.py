"""Closed-loop optimization cycle endpoints (Phase 12).

A cycle observes → simulates → optimizes → proposes → (approval) →
executes → measures → learns → completes. Execution is delegated to existing
systems after approval; the cycle itself records references only.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import AutonomousOptimizationCycle
from app.db.session import get_db  # noqa: B008
from app.phase12.loop import NEXUSOptimizationLoop
from app.schemas.phase12 import (
    OptimizationCycleCreate,
    OptimizationCyclePublic,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/optimization-cycles", tags=["closed-loop"])


def _identity_id(identity) -> UUID | None:
    return getattr(identity, "id", None)


def _loop(db: Session) -> NEXUSOptimizationLoop:
    return NEXUSOptimizationLoop(db)


@router.get("", response_model=list[OptimizationCyclePublic], status_code=200)
async def list_cycles(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    stmt = select(AutonomousOptimizationCycle)
    if company_id is not None:
        stmt = stmt.where(AutonomousOptimizationCycle.company_id == company_id)
    stmt = stmt.order_by(AutonomousOptimizationCycle.started_at.desc())
    rows = list(db.execute(stmt).scalars())
    return [OptimizationCyclePublic.model_validate(c) for c in rows]


@router.post("", response_model=OptimizationCyclePublic, status_code=201)
async def create_cycle(
    payload: OptimizationCycleCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    cycle = _loop(db).create_cycle(
        company_id=payload.company_id,
        name=payload.name,
        observe=payload.observe,
        created_by=_identity_id(identity),
    )
    return OptimizationCyclePublic.model_validate(cycle)


@router.get("/{cycle_id}", response_model=OptimizationCyclePublic, status_code=200)
async def get_cycle(
    cycle_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    cycle = _loop(db).get_cycle(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return OptimizationCyclePublic.model_validate(cycle)


@router.post("/{cycle_id}/run", response_model=OptimizationCyclePublic, status_code=201)
async def run_cycle(
    cycle_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    loop = _loop(db)
    loop.simulate(cycle_id)
    loop.optimize(cycle_id)
    loop.propose(cycle_id)
    cycle = loop.require_approval(cycle_id, requester_id=_identity_id(identity))
    return OptimizationCyclePublic.model_validate(cycle)


@router.post("/{cycle_id}/approve", response_model=OptimizationCyclePublic, status_code=200)
async def approve_cycle(
    cycle_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    loop = _loop(db)
    cycle = loop.get_cycle(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Cycle not found")
    if cycle.approval_gate_id:
        from app.startup.gates import ApprovalGateManager

        ApprovalGateManager(db).approve(
            company_id=cycle.company_id,
            gate_id=cycle.approval_gate_id,
            approver_id=_identity_id(identity),
        )
    cycle = loop.execute(cycle_id)
    return OptimizationCyclePublic.model_validate(cycle)


@router.post("/{cycle_id}/cancel", response_model=OptimizationCyclePublic, status_code=200)
async def cancel_cycle(
    cycle_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    cycle = _loop(db).cancel(cycle_id)
    return OptimizationCyclePublic.model_validate(cycle)


__all__ = ["router"]
