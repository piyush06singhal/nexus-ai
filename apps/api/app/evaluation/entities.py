"""Evaluation domain entities (Phase 6).

Shared dataclasses and enums for the evaluation framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class EvaluationTarget(StrEnum):
    """What an evaluation targets (spec §35)."""

    AGENT = "agent"
    TASK = "task"
    TOOL = "tool"
    WORKFLOW = "workflow"
    ORCHESTRATION = "orchestration"
    MODEL = "model"
    SYSTEM = "system"


@dataclass
class Evaluation:
    """A named evaluation suite definition (spec §35)."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    target_type: EvaluationTarget | None = None
    target_id: UUID | None = None
    description: str | None = None
    cases: list[EvaluationCase] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "target_type": self.target_type.value if self.target_type else None,
            "target_id": str(self.target_id) if self.target_id else None,
            "description": self.description,
            "case_count": len(self.cases),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EvaluationCase:
    """An individual evaluated case within an evaluation (spec §34)."""

    id: UUID = field(default_factory=uuid4)
    evaluation_id: UUID | None = None
    name: str = ""
    input: dict[str, Any] | None = None
    expected_outcome: dict[str, Any] | None = None
    criteria: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "evaluation_id": str(self.evaluation_id) if self.evaluation_id else None,
            "name": self.name,
            "input": self.input,
            "expected_outcome": self.expected_outcome,
            "criteria": self.criteria,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EvaluationMetric:
    """One named metric value associated with a run (spec §31)."""

    id: UUID = field(default_factory=uuid4)
    run_id: UUID | None = None
    metric_key: str = ""
    value: float = 0.0
    label: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "run_id": str(self.run_id) if self.run_id else None,
            "metric_key": self.metric_key,
            "value": self.value,
            "label": self.label,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EvaluationResult:
    """The outcome of one case within one run (spec §30)."""

    id: UUID = field(default_factory=uuid4)
    run_id: UUID | None = None
    case_id: UUID | None = None
    passed: bool = False
    score: float | None = None
    actual_outcome: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "run_id": str(self.run_id) if self.run_id else None,
            "case_id": str(self.case_id) if self.case_id else None,
            "passed": self.passed,
            "score": self.score,
            "actual_outcome": self.actual_outcome,
            "metrics": self.metrics,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EvaluationRun:
    """A single execution of an evaluation suite (spec §35)."""

    id: UUID = field(default_factory=uuid4)
    evaluation_id: UUID | None = None
    status: str = "running"
    score: float | None = None
    metrics: dict[str, Any] | None = None
    summary: str | None = None
    results: list[EvaluationResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "evaluation_id": str(self.evaluation_id) if self.evaluation_id else None,
            "status": self.status,
            "score": self.score,
            "metrics": self.metrics,
            "summary": self.summary,
            "result_count": len(self.results),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class RunComparison:
    """Result of comparing two evaluation runs (spec §36)."""

    run_a_id: UUID
    run_b_id: UUID
    score_a: float
    score_b: float
    delta: float
    per_metric_deltas: dict[str, float] = field(default_factory=dict)
    regression: bool = False
    regression_threshold: float = 0.05

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_a_id": str(self.run_a_id),
            "run_b_id": str(self.run_b_id),
            "score_a": self.score_a,
            "score_b": self.score_b,
            "delta": self.delta,
            "per_metric_deltas": self.per_metric_deltas,
            "regression": self.regression,
            "regression_threshold": self.regression_threshold,
        }


@dataclass
class RegressionReport:
    """A regression detection report (spec §37)."""

    status: str = "ok"  # ok | regression_detected
    previous_score: float = 0.0
    current_score: float = 0.0
    threshold: float = 0.05
    delta: float = 0.0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "previous_score": self.previous_score,
            "current_score": self.current_score,
            "threshold": self.threshold,
            "delta": self.delta,
            "message": self.message,
        }
