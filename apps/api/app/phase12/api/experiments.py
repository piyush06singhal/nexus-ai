"""Experiment endpoints (Phase 12) — approval-gated, isolated what-if analyses.

Experiments never modify production state; conclusions use measured-size honest
phrases (WINNER / LOSER / INCONCLUSIVE) with explicit sample-size + limitations.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db  # noqa: B008
from app.phase12.experiments import ExperimentEngine
from app.schemas.phase12 import (
    ExperimentCreate,
    ExperimentPublic,
    ExperimentResultPublic,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _identity_id(identity) -> UUID | None:
    return getattr(identity, "id", None)


def _engine(db: Session) -> ExperimentEngine:
    return ExperimentEngine(db)


@router.get("", response_model=list[ExperimentPublic], status_code=200)
async def list_experiments(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return [ExperimentPublic.model_validate(e) for e in _engine(db).list_experiments(company_id)]


@router.post("", response_model=ExperimentPublic, status_code=201)
async def create_experiment(
    payload: ExperimentCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    exp = _engine(db).create_experiment(
        company_id=payload.company_id,
        name=payload.name,
        description=payload.description,
        hypothesis=payload.hypothesis,
        sample_size=payload.sample_size,
        metrics=payload.metrics,
        baseline=payload.baseline,
        variants=payload.variants,
        created_by=_identity_id(identity),
    )
    return ExperimentPublic.model_validate(exp)


@router.get("/{experiment_id}", response_model=ExperimentPublic, status_code=200)
async def get_experiment(
    experiment_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    exp = _engine(db).get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ExperimentPublic.model_validate(exp)


@router.post("/{experiment_id}/submit", response_model=ExperimentPublic, status_code=200)
async def submit_experiment(
    experiment_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return ExperimentPublic.model_validate(_engine(db).submit_for_approval(experiment_id))


@router.post("/{experiment_id}/approve", response_model=ExperimentPublic, status_code=200)
async def approve_experiment(
    experiment_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return ExperimentPublic.model_validate(_engine(db).approve(experiment_id))


@router.post("/{experiment_id}/run", response_model=ExperimentPublic, status_code=200)
async def run_experiment(
    experiment_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return ExperimentPublic.model_validate(_engine(db).run_experiment(experiment_id))


@router.post("/{experiment_id}/stop", response_model=ExperimentPublic, status_code=200)
async def stop_experiment(
    experiment_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return ExperimentPublic.model_validate(_engine(db).stop_experiment(experiment_id))


@router.post(
    "/{experiment_id}/complete",
    response_model=ExperimentResultPublic,
    status_code=201,
)
async def complete_experiment(
    experiment_id: UUID,
    payload: dict,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    conclusion = payload.get("conclusion", "inconclusive")
    result = _engine(db).complete_experiment(
        experiment_id,
        conclusion=conclusion,
        winning_variant_id=(
            UUID(str(payload["winning_variant_id"])) if payload.get("winning_variant_id") else None
        ),
        metrics=payload.get("metrics"),
        confidence=payload.get("confidence"),
        assumptions=payload.get("assumptions"),
        limitations=payload.get("limitations"),
    )
    return ExperimentResultPublic.model_validate(result)


@router.get(
    "/{experiment_id}/results",
    response_model=list[ExperimentResultPublic],
    status_code=200,
)
async def experiment_results(
    experiment_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rows = _engine(db).get_results(experiment_id)
    return [ExperimentResultPublic.model_validate(r) for r in rows]


__all__ = ["router"]
