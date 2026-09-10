"""Evaluation package tests (Phase 6).

Covers entities, metrics, the default dataset, the runner (with persistence),
comparison, and regression detection. Uses the ``db`` fixture.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.models.reliability import EvaluationRun as EvaluationRunRow
from app.evaluation.comparison import compare_runs
from app.evaluation.dataset import build_default_dataset
from app.evaluation.entities import (
    RunComparison,
)
from app.evaluation.metrics import (
    compute_all_metrics,
    failure_rate,
    task_success_rate,
)
from app.evaluation.regression import RegressionDetector
from app.evaluation.runner import EvaluationRunner

# ── Metrics ───────────────────────────────────────────────────────────────────


def test_metrics_are_pure_functions():
    results = [
        {"status": "completed", "passed": True, "duration_ms": 100},
        {"status": "completed", "passed": True, "duration_ms": 200},
        {"status": "failed", "passed": False, "duration_ms": 300},
    ]
    assert task_success_rate(results) == pytest.approx(2 / 3)
    assert failure_rate(results) == pytest.approx(1 / 3)
    all_metrics = compute_all_metrics(results)
    assert "task_success_rate" in all_metrics
    assert "completion_time" in all_metrics


# ── Dataset ───────────────────────────────────────────────────────────────────


def test_default_dataset_has_eight_cases():
    suite = build_default_dataset()
    assert suite.name == "NEXUS Default Evaluation Suite"
    assert len(suite.cases) == 8


# ── Runner (persisted) ───────────────────────────────────────────────────────


def test_runner_executes_and_persists(db):
    runner = EvaluationRunner(db)
    suite = build_default_dataset()
    run = runner.run_evaluation(suite)

    assert run.status == "completed"
    assert run.score is not None
    assert len(run.results) == 8
    assert all(r.passed for r in run.results)  # deterministic mock matches expected
    assert run.metrics["task_success_rate"] == pytest.approx(1.0)

    # Persisted
    runs = runner.list_runs()
    assert len(runs) >= 1
    results = runner.list_results_for_run(run.id)
    assert len(results) == 8


def test_runner_failing_case(db):
    runner = EvaluationRunner(db)

    def always_fail(case):
        return {"wrong": "shape"}

    suite = build_default_dataset()
    run = runner.run_evaluation(suite, executor=always_fail)
    assert any(not r.passed for r in run.results)
    assert run.metrics["task_success_rate"] == 0.0


# ── Comparison ────────────────────────────────────────────────────────────────


def test_compare_runs_non_regression():
    run_a = EvaluationRunRow(id=uuid4(), evaluation_id=uuid4(), status="completed", score=0.95)
    run_b = EvaluationRunRow(id=uuid4(), evaluation_id=uuid4(), status="completed", score=0.96)
    comparison = compare_runs(run_a, run_b)
    assert isinstance(comparison, RunComparison)
    assert comparison.delta == pytest.approx(0.01)
    assert comparison.regression is False


def test_compare_runs_regression():
    run_a = EvaluationRunRow(id=uuid4(), evaluation_id=uuid4(), status="completed", score=0.95)
    run_b = EvaluationRunRow(id=uuid4(), evaluation_id=uuid4(), status="completed", score=0.80)
    comparison = compare_runs(run_a, run_b)
    assert comparison.regression is True
    assert comparison.delta == pytest.approx(-0.15)


# ── Regression detector ──────────────────────────────────────────────────────


def test_regression_detector_threshold():
    detector = RegressionDetector(threshold=0.05)
    report = detector.check(previous_score=0.95, current_score=0.88)
    assert report.status == "regression_detected"

    ok = detector.check(previous_score=0.90, current_score=0.93)
    assert ok.status == "ok"
    assert ok.message.startswith("No regression")


def test_regression_detector_series():
    detector = RegressionDetector(threshold=0.05)
    series = [0.9, 0.91, 0.92, 0.80, 0.81, 0.79]
    report = detector.check_metric_series(series)
    assert report.status in ("regression_detected", "ok")
    assert report.previous_score == pytest.approx(sum(series[-6:-3]) / 3)
