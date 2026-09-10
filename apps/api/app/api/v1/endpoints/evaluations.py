"""Evaluation endpoints (Phase 6, spec §41).

NOTE: literal ``/runs/...`` routes are declared BEFORE the ``/{evaluation_id}``
parameter route so FastAPI matches them correctly (a UUID parse of "runs"
would otherwise 422).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.evaluation.entities import Evaluation as EvaluationSuite
from app.evaluation.entities import EvaluationCase
from app.schemas.evaluation import (
    EvaluationComparisonRead,
    EvaluationCreate,
    EvaluationListResponse,
    EvaluationRead,
    EvaluationResultRead,
    EvaluationRunListResponse,
    EvaluationRunRead,
    RegressionReportRead,
)
from app.services.evaluation_service import (
    EvaluationService,
    evaluation_to_dict,
    result_to_dict,
    run_to_dict,
)

router = APIRouter(tags=["evaluations"], prefix="/evaluations")

# ── LIST (literal, no param) ─────────────────────────────────────────────────


@router.get("", response_model=EvaluationListResponse, summary="List evaluations")
def list_evaluations(
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> EvaluationListResponse:
    service = EvaluationService(db)
    evaluations = service.list_evaluations(limit=limit)
    return EvaluationListResponse(
        evaluations=[EvaluationRead.model_validate(evaluation_to_dict(e)) for e in evaluations],
        total=len(evaluations),
    )


# ── RUNS (literal, declared before /{evaluation_id}) ─────────────────────────


@router.get(
    "/runs",
    response_model=EvaluationRunListResponse,
    summary="List evaluation runs",
)
def list_runs(
    evaluation_id: UUID | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> EvaluationRunListResponse:
    service = EvaluationService(db)
    runs = service.list_runs(evaluation_id=evaluation_id, limit=limit)
    return EvaluationRunListResponse(
        runs=[EvaluationRunRead.model_validate(run_to_dict(r)) for r in runs],
        total=len(runs),
    )


@router.post("/runs", response_model=EvaluationRunRead, summary="Run an evaluation")
def run_evaluation(
    payload: EvaluationCreate | None = None,
    db: Session = Depends(get_db),  # noqa: B008
) -> EvaluationRunRead:
    service = EvaluationService(db)

    if payload and payload.cases:
        suite = EvaluationSuite(
            name=payload.name or "Custom Evaluation",
            target_type=payload.target_type,
            description=payload.description,
            cases=[
                EvaluationCase(
                    name=c.get("name", f"Case {i}"),
                    input=c.get("input"),
                    expected_outcome=c.get("expected_outcome"),
                    criteria=c.get("criteria", []),
                )
                for i, c in enumerate(payload.cases)
            ],
        )
        run = service.run_evaluation(suite)
    else:
        run = service.run_default_evaluation()

    return EvaluationRunRead.model_validate(run.to_dict())


@router.get(
    "/runs/compare",
    response_model=EvaluationComparisonRead,
    summary="Compare two evaluation runs",
)
def compare_runs(
    run_a: UUID = Query(...),  # noqa: B008
    run_b: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.schemas.evaluation import EvaluationComparisonRead

    service = EvaluationService(db)
    comparison = service.compare_runs(run_a, run_b)
    if comparison is None:
        raise HTTPException(status_code=404, detail="One or both runs not found")
    return EvaluationComparisonRead.model_validate(comparison.to_dict())


@router.get("/runs/{run_id}", response_model=EvaluationRunRead, summary="Get an evaluation run")
def get_run(
    run_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> EvaluationRunRead:
    service = EvaluationService(db)
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return EvaluationRunRead.model_validate(run_to_dict(run))


@router.get(
    "/runs/{run_id}/results",
    response_model=list[EvaluationResultRead],
    summary="List results for an evaluation run",
)
def get_run_results(
    run_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
):
    service = EvaluationService(db)
    results = service.list_results_for_run(run_id)
    return [EvaluationResultRead.model_validate(result_to_dict(r)) for r in results]


# ── REGRESSION (literal, before /{evaluation_id}) ────────────────────────────


@router.get(
    "/regression/check",
    response_model=RegressionReportRead,
    summary="Check for regression between two scores",
)
def check_regression(
    previous: float = Query(..., ge=0.0, le=1.0),  # noqa: B008
    current: float = Query(..., ge=0.0, le=1.0),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> RegressionReportRead:
    service = EvaluationService(db, regression_threshold=settings.evaluation_regression_threshold)
    report = service.check_regression(previous, current, label="api")
    return RegressionReportRead(
        status=report.status,
        previous_score=report.previous_score,
        current_score=report.current_score,
        threshold=report.threshold,
        delta=report.delta,
        message=report.message,
    )


# ── BY ID (declared last) ────────────────────────────────────────────────────


@router.get("/{evaluation_id}", response_model=EvaluationRead, summary="Get an evaluation")
def get_evaluation(
    evaluation_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> EvaluationRead:
    service = EvaluationService(db)
    row = service.get_evaluation(evaluation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return EvaluationRead.model_validate(evaluation_to_dict(row))
