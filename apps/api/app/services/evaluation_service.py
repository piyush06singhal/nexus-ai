"""Evaluation service (Phase 6).

Thin CRUD and lifecycle orchestration over the evaluation package. Mirrors the
`OrchestrationService` pattern. Coordinates running evaluations, listing runs,
comparison, and regression detection.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.evaluation.comparison import compare_runs_by_id
from app.evaluation.dataset import build_default_dataset
from app.evaluation.entities import Evaluation
from app.evaluation.regression import RegressionDetector
from app.evaluation.runner import EvaluationRunner


class EvaluationService:
    """Coordinates evaluation operations."""

    def __init__(self, db: Session, regression_threshold: float = 0.05) -> None:
        self.db = db
        self._runner = EvaluationRunner(db)
        self._regression_detector = RegressionDetector(threshold=regression_threshold)

    def run_default_evaluation(self, evaluation_id: UUID | None = None):
        """Run the default evaluation suite."""
        suite = build_default_dataset()
        if evaluation_id:
            suite.id = evaluation_id
        return self._runner.run_evaluation(suite)

    def run_evaluation(self, evaluation: Evaluation):
        return self._runner.run_evaluation(evaluation)

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_run(self, run_id: UUID):
        return self._runner.get_run(run_id)

    def get_evaluation(self, evaluation_id: UUID):
        return self._runner.get_evaluation(evaluation_id)

    def list_runs(self, evaluation_id: UUID | None = None, limit: int = 50):
        return self._runner.list_runs(evaluation_id=evaluation_id, limit=limit)

    def list_evaluations(self, limit: int = 50):
        return self._runner.list_evaluations(limit=limit)

    def list_results_for_run(self, run_id: UUID):
        return self._runner.list_results_for_run(run_id)

    # ── Comparison & regression ───────────────────────────────────────────────

    def compare_runs(self, run_a_id: UUID, run_b_id: UUID):
        return compare_runs_by_id(self.db, run_a_id, run_b_id)

    def check_regression(
        self, previous_score: float, current_score: float, label: str | None = None
    ):
        return self._regression_detector.check(previous_score, current_score, label)


def run_to_dict(run) -> dict:
    """Serialize an evaluation run to a dict."""
    import json

    return {
        "id": str(run.id),
        "evaluation_id": str(run.evaluation_id) if run.evaluation_id else None,
        "status": run.status,
        "score": run.score,
        "metrics": json.loads(run.metrics) if run.metrics else None,
        "summary": run.summary,
        "created_at": run.created_at,
    }


def evaluation_to_dict(eval_row) -> dict:
    """Serialize an evaluation to a dict."""
    return {
        "id": str(eval_row.id),
        "name": eval_row.name,
        "target_type": eval_row.target_type,
        "target_id": str(eval_row.target_id) if eval_row.target_id else None,
        "description": eval_row.description,
        "created_at": eval_row.created_at,
    }


def result_to_dict(result) -> dict:
    """Serialize an evaluation result to a dict."""
    import json

    return {
        "id": str(result.id),
        "run_id": str(result.run_id),
        "case_id": str(result.case_id) if result.case_id else None,
        "passed": result.passed,
        "score": result.score,
        "actual_outcome": json.loads(result.actual_outcome) if result.actual_outcome else None,
        "metrics": json.loads(result.metrics) if result.metrics else None,
        "error": result.error,
        "created_at": result.created_at,
    }
