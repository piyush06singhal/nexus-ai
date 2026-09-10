"""Evaluation package (Phase 6).

Provides the evaluation framework for measuring NEXUS system performance:
entities, metrics, datasets, runners, comparison, and regression detection.
"""

from app.evaluation.entities import (
    Evaluation,
    EvaluationCase,
    EvaluationMetric,
    EvaluationResult,
    EvaluationRun,
    EvaluationTarget,
)

__all__ = [
    "Evaluation",
    "EvaluationCase",
    "EvaluationMetric",
    "EvaluationResult",
    "EvaluationRun",
    "EvaluationTarget",
]
