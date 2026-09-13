"""Optimization endpoints (Phase 12) — problems, runs, explainable recommendations.

Every recommendation carries the §46 explainability block and flows through
approval before any execution; optimization itself never mutates production
state.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import OptimizationCandidate, OptimizationRecommendation
from app.db.session import get_db  # noqa: B008
from app.phase12.optimization import (
    Constraint,
    Objective,
    OptimizationEngine,
    Variable,
)
from app.schemas.phase12 import (
    OptimizationProblemCreate,
    OptimizationProblemPublic,
    OptimizationResultsPublic,
    OptimizationRunPublic,
    RecommendationPublic,
    RecommendationReject,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/optimization", tags=["optimization"])


def _identity_id(identity) -> UUID | None:
    return getattr(identity, "id", None)


def _engine(db: Session) -> OptimizationEngine:
    return OptimizationEngine(db)


@router.get("/problems", response_model=list[OptimizationProblemPublic], status_code=200)
async def list_problems(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return [
        OptimizationProblemPublic.model_validate(p) for p in _engine(db).list_problems(company_id)
    ]


@router.post("/problems", response_model=OptimizationProblemPublic, status_code=201)
async def create_problem(
    payload: OptimizationProblemCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    objectives = [
        Objective(metric=o.metric, direction=o.direction, weight=o.weight)
        for o in payload.objectives
    ]
    variables = [
        Variable(
            name=v.name,
            kind=v.kind,
            low=v.low,
            high=v.high,
            default=v.default,
            options=v.options or [],
        )
        for v in payload.variables
    ]
    # Wire-level constraints are informational specs (name/description). The
    # engine enforces real bounds via PolicyEngine + ResourceGovernanceService
    # at run time, so candidates can never violate policy or resource limits.
    constraints = [
        Constraint(
            name=c.get("name", f"constraint-{i}"),
            check=lambda _raw: True,
            description=c.get("description"),
        )
        for i, c in enumerate(payload.constraints or [])
    ]
    problem = _engine(db).create_problem(
        company_id=payload.company_id,
        name=payload.name,
        description=payload.description,
        strategy=payload.strategy or "greedy",
        objectives=objectives,
        variables=variables,
        constraints=constraints,
        created_by=_identity_id(identity),
    )
    return OptimizationProblemPublic.model_validate(problem)


@router.get("/problems/{problem_id}", response_model=OptimizationProblemPublic, status_code=200)
async def get_problem(
    problem_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    problem = _engine(db).get_problem(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Optimization problem not found")
    return OptimizationProblemPublic.model_validate(problem)


@router.post("/problems/{problem_id}/run", response_model=OptimizationRunPublic, status_code=201)
async def run_problem(
    problem_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return OptimizationRunPublic.model_validate(_engine(db).run_problem(problem_id))


@router.get("/runs/{run_id}", response_model=OptimizationRunPublic, status_code=200)
async def get_run(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    run = _engine(db).get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    return OptimizationRunPublic.model_validate(run)


@router.get("/runs/{run_id}/results", response_model=OptimizationResultsPublic, status_code=200)
async def run_results(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rows = list(
        db.execute(
            select(OptimizationCandidate)
            .where(OptimizationCandidate.run_id == run_id)
            .order_by(OptimizationCandidate.candidate_index)
        ).scalars()
    )
    candidates = [
        {
            "index": c.candidate_index,
            "values": c.values_json,
            "scores": c.objective_scores_json,
        }
        for c in rows
    ]
    return OptimizationResultsPublic(
        run_id=run_id,
        candidates=candidates,
        best_candidate=candidates[0] if candidates else None,
    )


@router.get("/recommendations", response_model=list[RecommendationPublic], status_code=200)
async def list_recommendations(
    company_id: UUID | None = None,
    status: str | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    stmt = select(OptimizationRecommendation).order_by(OptimizationRecommendation.created_at.desc())
    if company_id is not None:
        stmt = stmt.where(OptimizationRecommendation.company_id == company_id)
    if status is not None:
        stmt = stmt.where(OptimizationRecommendation.status == status)
    rows = list(db.execute(stmt).scalars())
    return [RecommendationPublic.model_validate(r) for r in rows]


@router.post("/runs/{run_id}/recommend", response_model=RecommendationPublic, status_code=201)
async def recommend(
    run_id: UUID,
    payload: dict,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    company_id = payload.get("company_id")
    title = payload.get("title", f"Recommendation for run {run_id}")
    rec = _engine(db).recommend(
        run_id=run_id,
        company_id=UUID(str(company_id)) if company_id else None,
        title=title,
        created_by=_identity_id(identity),
    )
    return RecommendationPublic.model_validate(rec)


@router.get("/recommendations/{rec_id}", response_model=RecommendationPublic, status_code=200)
async def get_recommendation(
    rec_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rec = db.get(OptimizationRecommendation, rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return RecommendationPublic.model_validate(rec)


@router.post(
    "/recommendations/{rec_id}/approve",
    response_model=RecommendationPublic,
    status_code=200,
)
async def approve_recommendation(
    rec_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rec = _engine(db).approve_rec(rec_id, approver_id=_identity_id(identity))
    return RecommendationPublic.model_validate(rec)


@router.post(
    "/recommendations/{rec_id}/reject",
    response_model=RecommendationPublic,
    status_code=200,
)
async def reject_recommendation(
    rec_id: UUID,
    payload: RecommendationReject | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rec = _engine(db).reject_rec(rec_id, reason=payload.reason if payload else None)
    return RecommendationPublic.model_validate(rec)


__all__ = ["router"]
