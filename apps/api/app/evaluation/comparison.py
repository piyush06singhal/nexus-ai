"""Evaluation run comparison (Phase 6, spec §36).

Compares two evaluation runs to detect improvements or regressions.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.reliability import EvaluationRun as EvaluationRunRow
from app.evaluation.entities import RunComparison


def _loads(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def compare_runs(
    run_a: EvaluationRunRow,
    run_b: EvaluationRunRow,
    threshold: float = 0.05,
) -> RunComparison:
    """Compare two evaluation runs (§36).

    Args:
        run_a: First (baseline) run.
        run_b: Second (current) run.
        threshold: Regression threshold — if score_b < score_a - threshold, it's a regression.

    Returns:
        A :class:`RunComparison` with the comparison results.
    """
    score_a = run_a.score or 0.0
    score_b = run_b.score or 0.0
    delta = score_b - score_a

    # Per-metric deltas
    metrics_a = _loads(run_a.metrics)
    metrics_b = _loads(run_b.metrics)

    all_keys = set(metrics_a.keys()) | set(metrics_b.keys())
    per_metric_deltas: dict[str, float] = {}
    for key in all_keys:
        val_a = metrics_a.get(key, 0.0)
        val_b = metrics_b.get(key, 0.0)
        per_metric_deltas[key] = round(val_b - val_a, 4)

    regression = delta < -threshold

    return RunComparison(
        run_a_id=run_a.id,
        run_b_id=run_b.id,
        score_a=score_a,
        score_b=score_b,
        delta=round(delta, 4),
        per_metric_deltas=per_metric_deltas,
        regression=regression,
        regression_threshold=threshold,
    )


def compare_runs_by_id(
    db: Session,
    run_a_id: UUID,
    run_b_id: UUID,
    threshold: float = 0.05,
) -> RunComparison | None:
    """Compare two evaluation runs by ID."""
    run_a = db.get(EvaluationRunRow, run_a_id)
    run_b = db.get(EvaluationRunRow, run_b_id)
    if not run_a or not run_b:
        return None
    return compare_runs(run_a, run_b, threshold)
