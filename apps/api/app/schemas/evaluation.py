"""Pydantic API schemas for evaluation (Phase 6).

Mirror the evaluation ORM models but stay decoupled from SQLAlchemy so they
can validate API input and serialize API output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EvaluationCreate(BaseModel):
    """Payload to create/run an evaluation."""

    name: str | None = None
    target_type: str | None = None
    target_id: UUID | None = None
    description: str | None = None
    use_default_dataset: bool = True
    cases: list[dict[str, Any]] | None = None


class EvaluationRead(BaseModel):
    """Evaluation representation returned by the API."""

    id: UUID
    name: str
    target_type: str | None = None
    target_id: UUID | None = None
    description: str | None = None
    case_count: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationRunRead(BaseModel):
    """Evaluation run representation returned by the API."""

    id: UUID
    evaluation_id: UUID | None = None
    status: str
    score: float | None = None
    metrics: dict[str, Any] | None = None
    summary: str | None = None
    result_count: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationResultRead(BaseModel):
    """Evaluation result representation returned by the API."""

    id: UUID
    run_id: UUID
    case_id: UUID | None = None
    passed: bool
    score: float | None = None
    actual_outcome: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationComparisonRead(BaseModel):
    """Evaluation run comparison representation returned by the API."""

    run_a_id: UUID
    run_b_id: UUID
    score_a: float
    score_b: float
    delta: float
    per_metric_deltas: dict[str, float] = {}
    regression: bool
    regression_threshold: float


class RegressionReportRead(BaseModel):
    """Regression detection report returned by the API."""

    status: str
    previous_score: float
    current_score: float
    threshold: float
    delta: float
    message: str


class EvaluationListResponse(BaseModel):
    """Paginated (simple) list of evaluations."""

    evaluations: list[EvaluationRead]
    total: int


class EvaluationRunListResponse(BaseModel):
    """Paginated (simple) list of evaluation runs."""

    runs: list[EvaluationRunRead]
    total: int
