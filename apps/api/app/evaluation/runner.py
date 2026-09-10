"""Evaluation runner (Phase 6, spec §35).

Executes a set of evaluation cases, persists results and metrics,
and returns an :class:`EvaluationRun`. Sync-inline execution for
deterministic ordering (mirrors the workflow/orchestration pattern).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.db.models.reliability import (
    Evaluation as EvaluationRow,
)
from app.db.models.reliability import (
    EvaluationCase as EvaluationCaseRow,
)
from app.db.models.reliability import (
    EvaluationMetric as EvaluationMetricRow,
)
from app.db.models.reliability import (
    EvaluationResult as EvaluationResultRow,
)
from app.db.models.reliability import (
    EvaluationRun as EvaluationRunRow,
)
from app.evaluation.entities import (
    Evaluation,
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
)
from app.evaluation.metrics import compute_all_metrics


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


class EvaluationRunner:
    """Executes evaluation suites and persists results (§35)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def run_evaluation(
        self,
        evaluation: Evaluation,
        executor: Any = None,
    ) -> EvaluationRun:
        """Run an evaluation suite.

        Args:
            evaluation: The evaluation suite to run.
            executor: Optional callable that runs a case and returns actual_outcome.
                      If None, uses deterministic mock evaluation.

        Returns:
            The completed :class:`EvaluationRun` with results and metrics.
        """
        # Persist evaluation
        eval_row = self._persist_evaluation(evaluation)

        # Create run
        run = EvaluationRun(
            id=uuid4(),
            evaluation_id=evaluation.id,
            status="running",
        )
        run_row = EvaluationRunRow(
            id=run.id,
            evaluation_id=eval_row.id,
            status="running",
        )
        self.db.add(run_row)
        self.db.flush()

        results: list[EvaluationResult] = []
        case_results_raw: list[dict[str, Any]] = []

        for case in evaluation.cases:
            result = self._run_case(case, executor)
            results.append(result)
            case_results_raw.append(result.to_dict())

            # Persist case result
            result_row = EvaluationResultRow(
                id=result.id,
                run_id=run.id,
                case_id=case.id,
                passed=result.passed,
                score=result.score,
                actual_outcome=_dumps(result.actual_outcome),
                metrics=_dumps(result.metrics),
                error=result.error,
            )
            self.db.add(result_row)

        # Compute aggregate metrics
        metrics = compute_all_metrics(case_results_raw)
        score = self._compute_aggregate_score(results)

        # Update run
        run_row.status = "completed"
        run_row.score = score
        run_row.metrics = _dumps(metrics)
        run_row.summary = _build_summary(results, metrics)

        # Persist individual metrics
        for key, value in metrics.items():
            metric_row = EvaluationMetricRow(
                id=uuid4(),
                run_id=run.id,
                metric_key=key,
                value=float(value),
                label=key.replace("_", " ").title(),
            )
            self.db.add(metric_row)

        self.db.flush()

        return EvaluationRun(
            id=run.id,
            evaluation_id=evaluation.id,
            status="completed",
            score=score,
            metrics=metrics,
            summary=run_row.summary,
            results=results,
            created_at=run_row.created_at,
        )

    def _run_case(
        self,
        case: EvaluationCase,
        executor: Any = None,
    ) -> EvaluationResult:
        """Run a single evaluation case."""
        try:
            if executor:
                actual = executor(case)
            else:
                actual = self._deterministic_evaluate(case)

            # Check criteria
            passed = self._check_criteria(actual, case.criteria)
            score = self._compute_case_score(actual, case.criteria, case.expected_outcome)

            return EvaluationResult(
                id=uuid4(),
                case_id=case.id,
                passed=passed,
                score=score,
                actual_outcome=actual,
                metrics={"case": case.name},
            )
        except Exception as exc:
            return EvaluationResult(
                id=uuid4(),
                case_id=case.id,
                passed=False,
                score=0.0,
                error=str(exc),
            )

    def _deterministic_evaluate(self, case: EvaluationCase) -> dict[str, Any]:
        """Deterministic mock evaluation — returns expected_outcome."""
        return case.expected_outcome or {}

    def _check_criteria(
        self,
        actual: dict[str, Any],
        criteria: list[dict[str, Any]],
    ) -> bool:
        """Check if actual matches all criteria."""
        for c in criteria:
            key = c.get("key", "")
            op = c.get("type", c.get("op", "eq"))
            expected = c.get("expected")
            value = actual.get(key)

            if op in ("eq", "equality"):
                if value != expected:
                    return False
            elif op == "ne":
                if value == expected:
                    return False
            elif op in ("gte", ">="):
                if value is None or value < expected:
                    return False
            elif op in ("lte", "<="):
                if value is None or value > expected:
                    return False
            elif op == "contains":
                if value is None or expected not in value:
                    return False
            elif op == "in":
                if value not in (expected or []):
                    return False
            elif op == "type_check":
                # Simplified type check
                pass
        return True

    def _compute_case_score(
        self,
        actual: dict[str, Any],
        criteria: list[dict[str, Any]],
        expected: dict[str, Any] | None,
    ) -> float:
        """Compute a score for a case based on criteria matches."""
        if not criteria:
            return 1.0 if actual == expected else 0.0

        passed = 0
        for c in criteria:
            key = c.get("key", "")
            op = c.get("type", c.get("op", "eq"))
            exp = c.get("expected")
            val = actual.get(key)

            if op in ("eq", "equality") and val == exp:
                passed += 1
            elif op == "ne" and val != exp:
                passed += 1
            elif op in ("gte", ">=") and val is not None and val >= exp:
                passed += 1
            elif op == "contains" and val is not None and exp in val:
                passed += 1
            elif op == "in" and val in (exp or []):
                passed += 1

        return round(passed / max(len(criteria), 1), 4)

    def _compute_aggregate_score(self, results: list[EvaluationResult]) -> float:
        """Compute aggregate score across all results."""
        if not results:
            return 0.0
        scores = [r.score or 0.0 for r in results]
        return round(sum(scores) / len(scores), 4)

    def _persist_evaluation(self, evaluation: Evaluation) -> EvaluationRow:
        """Persist an evaluation suite."""
        row = EvaluationRow(
            id=evaluation.id,
            name=evaluation.name,
            target_type=evaluation.target_type.value if evaluation.target_type else None,
            target_id=evaluation.target_id,
            description=evaluation.description,
        )
        self.db.add(row)

        # Persist cases
        for case in evaluation.cases:
            case_row = EvaluationCaseRow(
                id=case.id,
                evaluation_id=evaluation.id,
                name=case.name,
                input=_dumps(case.input),
                expected_outcome=_dumps(case.expected_outcome),
                criteria=_dumps(case.criteria),
            )
            self.db.add(case_row)

        self.db.flush()
        return row

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_run(self, run_id: UUID) -> EvaluationRunRow | None:
        return self.db.get(EvaluationRunRow, run_id)

    def get_evaluation(self, evaluation_id: UUID) -> EvaluationRow | None:
        return self.db.get(EvaluationRow, evaluation_id)

    def list_runs(
        self,
        evaluation_id: UUID | None = None,
        limit: int = 50,
    ) -> list[EvaluationRunRow]:
        from sqlalchemy import select

        stmt = select(EvaluationRunRow)
        if evaluation_id:
            stmt = stmt.where(EvaluationRunRow.evaluation_id == evaluation_id)
        stmt = stmt.order_by(EvaluationRunRow.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def list_evaluations(self, limit: int = 50) -> list[EvaluationRow]:
        from sqlalchemy import select

        stmt = select(EvaluationRow).order_by(EvaluationRow.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def list_results_for_run(self, run_id: UUID) -> list[EvaluationResultRow]:
        from sqlalchemy import select

        stmt = (
            select(EvaluationResultRow)
            .where(EvaluationResultRow.run_id == run_id)
            .order_by(EvaluationResultRow.created_at)
        )
        return list(self.db.execute(stmt).scalars().all())


def _build_summary(results: list[EvaluationResult], metrics: dict[str, float]) -> str:
    """Build a human-readable summary of the evaluation run."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and not r.error)
    errors = sum(1 for r in results if r.error)

    parts = [
        f"{total} cases: {passed} passed, {failed} failed, {errors} errors",
        f"Overall score: {metrics.get('task_success_rate', 0):.1%}",
    ]

    if metrics.get("failure_rate", 0) > 0:
        parts.append(f"Failure rate: {metrics['failure_rate']:.1%}")

    return "; ".join(parts)
