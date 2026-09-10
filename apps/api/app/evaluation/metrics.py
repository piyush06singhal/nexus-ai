"""Evaluation metrics (Phase 6, spec §31–§33).

Named metric functions that are pure functions over query results. Each returns
a float between 0.0 and 1.0 (or a raw count/cost where appropriate).
"""

from __future__ import annotations

from typing import Any


def task_success_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of tasks that completed successfully (§31)."""
    if not results:
        return 0.0
    passed = sum(1 for r in results if r.get("passed") or r.get("status") == "completed")
    return passed / len(results)


def verification_pass_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of verification runs that passed (§31)."""
    if not results:
        return 0.0
    passed = sum(1 for r in results if r.get("status") == "pass")
    return passed / len(results)


def recovery_success_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of recovery attempts that succeeded (§31)."""
    if not results:
        return 0.0
    recovered = sum(1 for r in results if r.get("outcome") == "recovered")
    return recovered / len(results)


def retry_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of executions that required retries (§31)."""
    if not results:
        return 0.0
    retried = sum(1 for r in results if r.get("attempt_number", 1) > 1)
    return retried / len(results)


def failure_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of executions that failed (§31)."""
    if not results:
        return 0.0
    failed = sum(1 for r in results if r.get("status") in ("failed", "error"))
    return failed / len(results)


def intervention_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of executions that required human intervention (§31)."""
    if not results:
        return 0.0
    escalated = sum(1 for r in results if r.get("status") == "escalated")
    return escalated / len(results)


def completion_time(results: list[dict[str, Any]]) -> float:
    """Average completion time in seconds (§31)."""
    if not results:
        return 0.0
    times = [r.get("duration_ms", 0) / 1000.0 for r in results if r.get("duration_ms")]
    if not times:
        return 0.0
    return sum(times) / len(times)


def token_cost(results: list[dict[str, Any]]) -> float:
    """Total token cost across all results (§31)."""
    return sum(r.get("tokens_used", 0) for r in results)


def efficiency(results: list[dict[str, Any]]) -> float:
    """Useful output per total cost: passed / total (§31)."""
    if not results:
        return 0.0
    passed = sum(1 for r in results if r.get("passed") or r.get("status") == "completed")
    return passed / max(len(results), 1)


def time_efficiency(results: list[dict[str, Any]]) -> float:
    """Useful output per unit time: passed_count / total_time (§31)."""
    if not results:
        return 0.0
    passed = sum(1 for r in results if r.get("passed") or r.get("status") == "completed")
    total_time = sum(r.get("duration_ms", 0) for r in results) / 1000.0
    if total_time <= 0:
        return 0.0
    return round(passed / total_time, 6)


# ── Agent-level metrics (§32) ────────────────────────────────────────────────


def agent_task_success_rate(
    results: list[dict[str, Any]],
    agent_id: str | None = None,
) -> float:
    """Task success rate for a specific agent."""
    if agent_id:
        results = [r for r in results if r.get("agent_id") == agent_id]
    return task_success_rate(results)


def agent_verification_rate(
    results: list[dict[str, Any]],
    agent_id: str | None = None,
) -> float:
    """Verification pass rate for a specific agent."""
    if agent_id:
        results = [r for r in results if r.get("agent_id") == agent_id]
    return verification_pass_rate(results)


# ── Model-level metrics (§33) ────────────────────────────────────────────────


def model_success_rate(
    results: list[dict[str, Any]],
    model_id: str | None = None,
) -> float:
    """Success rate for a specific model."""
    if model_id:
        results = [r for r in results if r.get("model_id") == model_id]
    return task_success_rate(results)


def model_cost_per_task(results: list[dict[str, Any]]) -> float:
    """Average token cost per task."""
    if not results:
        return 0.0
    total = token_cost(results)
    return round(total / len(results), 2)


# ── Metric registry ──────────────────────────────────────────────────────────

METRIC_REGISTRY: dict[str, Any] = {
    "task_success_rate": task_success_rate,
    "verification_pass_rate": verification_pass_rate,
    "recovery_success_rate": recovery_success_rate,
    "retry_rate": retry_rate,
    "failure_rate": failure_rate,
    "intervention_rate": intervention_rate,
    "completion_time": completion_time,
    "token_cost": token_cost,
    "efficiency": efficiency,
    "time_efficiency": time_efficiency,
}


def compute_all_metrics(results: list[dict[str, Any]]) -> dict[str, float]:
    """Compute all registered metrics over a result set."""
    return {key: fn(results) for key, fn in METRIC_REGISTRY.items()}
