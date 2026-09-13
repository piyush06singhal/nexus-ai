"""Benchmark endpoints (Phase 12) — suites, cases, runs, agent scores.

Reuses EvaluationRunner metrics (Phase 6); determinism via fixed datasets and
seeded scoring. Results are versioned for per-agent comparison.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db  # noqa: B008
from app.phase12.benchmarking import BenchmarkEngine, BenchmarkError
from app.schemas.phase12 import (
    AgentBenchmarkScorePublic,
    BenchmarkCreate,
    BenchmarkPublic,
    BenchmarkResultsPublic,
    BenchmarkRunPublic,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


def _identity_id(identity) -> UUID | None:
    return getattr(identity, "id", None)


def _engine(db: Session) -> BenchmarkEngine:
    return BenchmarkEngine(db)


@router.get("", response_model=list[BenchmarkPublic], status_code=200)
async def list_benchmarks(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return [BenchmarkPublic.model_validate(b) for b in _engine(db).list_benchmarks(company_id)]


@router.post("", response_model=BenchmarkPublic, status_code=201)
async def create_benchmark(
    payload: BenchmarkCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    bench = _engine(db).create_benchmark(
        company_id=payload.company_id,
        name=payload.name,
        description=payload.description,
        version=payload.version,
        dimensions=payload.dimensions,
        cases=payload.cases,
        created_by=_identity_id(identity),
    )
    return BenchmarkPublic.model_validate(bench)


@router.get("/{benchmark_id}", response_model=BenchmarkPublic, status_code=200)
async def get_benchmark(
    benchmark_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    bench = _engine(db).get_benchmark(benchmark_id)
    if bench is None:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return BenchmarkPublic.model_validate(bench)


@router.post("/{benchmark_id}/run", response_model=BenchmarkRunPublic, status_code=201)
async def run_benchmark(
    benchmark_id: UUID,
    payload: dict,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    agent_id = payload.get("agent_id")
    run = _engine(db).run_benchmark(
        benchmark_id,
        agent_id=UUID(str(agent_id)) if agent_id else None,
        agent_version=payload.get("agent_version"),
        company_id=(UUID(str(payload["company_id"])) if payload.get("company_id") else None),
        dimensions=payload.get("dimensions"),
    )
    return BenchmarkRunPublic.model_validate(run)


@router.get("/runs/{run_id}", response_model=BenchmarkRunPublic, status_code=200)
async def get_benchmark_run(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    run = _engine(db).get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return BenchmarkRunPublic.model_validate(run)


@router.get("/runs/{run_id}/results", response_model=BenchmarkResultsPublic, status_code=200)
async def benchmark_results(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    try:
        data = _engine(db).run_results(run_id)
    except BenchmarkError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BenchmarkResultsPublic(**dict(data))


@router.get(
    "/agents/{agent_id}/scores",
    response_model=list[AgentBenchmarkScorePublic],
    status_code=200,
)
async def agent_scores(
    agent_id: UUID,
    benchmark_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rows = _engine(db).agent_scores(agent_id, benchmark_id=benchmark_id)
    return [AgentBenchmarkScorePublic.model_validate(r) for r in rows]


__all__ = ["router"]
