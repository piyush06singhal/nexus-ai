"""Recovery package tests (Phase 6).

Covers the failure taxonomy, diagnosis, safety classifier, state machine,
planner, escalation service, budget, partial completion, the recovery engine,
and failure injection. Uses the ``db`` fixture for persistence checks.
"""

from __future__ import annotations

import pytest

from app.recovery.budget import BudgetTracker, ExecutionBudget
from app.recovery.diagnosis import HeuristicDiagnoser
from app.recovery.engine import RecoveryEngine
from app.recovery.escalation import EscalationService
from app.recovery.failure_injection import (
    FailInjectionSpec,
    InjectionKind,
    MockProvider,
    MockToolExecutor,
)
from app.recovery.partial import PartialCompletionBuilder
from app.recovery.planner import RecoveryPlanner
from app.recovery.safety import RetrySafety, SideEffectKind
from app.recovery.state_machine import InvalidTransitionError, RecoveryStateMachine
from app.recovery.strategy import RecoveryStrategy, strategy_backoff_ms
from app.recovery.taxonomy import FailureCategory, FailureSeverity, is_retryable
from app.recovery.types import EscalationContext, RecoveryState

# ── Taxonomy ──────────────────────────────────────────────────────────────────


def test_taxonomy_retryability():
    assert is_retryable(FailureCategory.TIMEOUT, FailureSeverity.MEDIUM) is True
    assert is_retryable(FailureCategory.PERMISSION_FAILURE, FailureSeverity.HIGH) is False
    assert is_retryable(FailureCategory.SYSTEM_FAILURE, FailureSeverity.CRITICAL) is False


# ── Diagnosis ─────────────────────────────────────────────────────────────────


def test_heuristic_diagnoser_timeout():
    diagnoser = HeuristicDiagnoser()
    diag = diagnoser.diagnose(
        error_text="Tool timeout",
        exception_type="TimeoutError",
        tool_call_status="timeout",
    )
    assert diag.category == FailureCategory.TIMEOUT.value
    assert diag.retryable is True


def test_heuristic_diagnoser_permission():
    diagnoser = HeuristicDiagnoser()
    diag = diagnoser.diagnose(error_text="Permission denied", exception_type="PermissionError")
    assert diag.category == FailureCategory.PERMISSION_FAILURE.value
    assert diag.retryable is False
    assert diag.recommended_strategy == "escalate"


# ── Safety ────────────────────────────────────────────────────────────────────


def test_retry_safety_high_risk():
    safety = RetrySafety()
    verdict = safety.evaluate(tool_name="delete_file")
    assert verdict.safe_to_retry is False
    assert verdict.side_effect == SideEffectKind.HIGH_RISK


def test_retry_safety_read_only():
    safety = RetrySafety(idempotent_tools={"web_search"})
    verdict = safety.evaluate(tool_name="web_search")
    assert verdict.safe_to_retry is True


def test_retry_safety_denied_status():
    safety = RetrySafety()
    verdict = safety.evaluate(tool_name="web_search", tool_result_status="denied")
    assert verdict.safe_to_retry is False


# ── State machine ─────────────────────────────────────────────────────────────


def test_state_machine_valid_flow():
    sm = RecoveryStateMachine()
    sm.transition(RecoveryState.CLASSIFIED, reason="detected")
    sm.transition(RecoveryState.RECOVERY_PLANNED, reason="planned")
    sm.transition(RecoveryState.RECOVERING, reason="recovering")
    sm.transition(RecoveryState.RETRYING, reason="retrying")
    sm.transition(RecoveryState.REVERIFIED, reason="reverified")
    sm.transition(RecoveryState.RECOVERED, reason="done")
    assert sm.state == RecoveryState.RECOVERED
    assert sm.is_terminal
    assert len(sm.timeline) == 6


def test_state_machine_invalid_transition():
    sm = RecoveryStateMachine()
    with pytest.raises(InvalidTransitionError):
        sm.transition(RecoveryState.RECOVERED, reason="illegal jump")


# ── Planner ───────────────────────────────────────────────────────────────────


def test_planner_non_retryable_escalates():
    from app.recovery.types import FailureDiagnosis

    planner = RecoveryPlanner(max_attempts=3)
    diag = FailureDiagnosis(
        category=FailureCategory.PERMISSION_FAILURE.value,
        severity=FailureSeverity.HIGH.value,
        retryable=False,
    )
    plan = planner.plan(diag)
    assert plan.strategy == RecoveryStrategy.ESCALATE


def test_planner_retryable_plans_retry():
    from app.recovery.types import FailureDiagnosis

    planner = RecoveryPlanner(max_attempts=3)
    diag = FailureDiagnosis(
        category=FailureCategory.TIMEOUT.value,
        severity=FailureSeverity.MEDIUM.value,
        retryable=True,
    )
    plan = planner.plan(diag)
    assert plan.strategy in (RecoveryStrategy.RETRY, RecoveryStrategy.RETRY_WITH_BACKOFF)


# ── Budget ────────────────────────────────────────────────────────────────────


def test_budget_exhaustion():
    budget = ExecutionBudget(max_retries=2)
    tracker = BudgetTracker(budget)
    assert tracker.can_retry() is True
    tracker.consume_retry()
    tracker.consume_retry()
    assert tracker.can_retry() is False
    assert tracker.exhausted() is True
    assert "Retry budget" in tracker.exhausted_reason()


# ── Partial completion ────────────────────────────────────────────────────────


def test_partial_completion_builder():
    builder = PartialCompletionBuilder()
    partial = builder.build(
        completed_tasks=["task_0", "task_1", "task_2"],
        failed_tasks=["task_3"],
        total_tasks=5,
    )
    assert partial.confidence == 0.6
    assert len(partial.remaining_actions) >= 1


# ── Escalation service (persisted) ────────────────────────────────────────────


def test_escalation_lifecycle(db):
    service = EscalationService(db)
    ctx = EscalationContext(
        issue="Critical failure needs review",
        category="system_failure",
        severity="critical",
    )
    esc = service.create(ctx)
    assert esc.state.value == "pending_human_review"

    # Agent cannot approve its own escalation — human decision via service
    approved = service.approve(esc.id, decision_reason="human approved")
    assert approved.state.value == "approved"

    # Already reviewed -> cannot re-review
    assert service.approve(esc.id) is None


# ── Recovery engine (persisted) ──────────────────────────────────────────────


def test_recovery_engine_retry(db):
    engine = RecoveryEngine(db)
    attempt = engine.recover(
        __import__("uuid").uuid4(),
        error_text="Tool timed out",
        exception_type="TimeoutError",
        tool_call_status="timeout",
    )
    assert attempt.outcome == "recovered"
    assert attempt.state.value == "recovered"


def test_recovery_engine_escalate(db):
    engine = RecoveryEngine(db)
    attempt = engine.recover(
        __import__("uuid").uuid4(),
        error_text="Permission denied",
        exception_type="PermissionError",
    )
    assert attempt.state.value in ("escalated", "aborted")
    assert attempt.outcome in ("escalated", None)


# ── Failure injection ─────────────────────────────────────────────────────────


def test_failure_injection_timeout():
    spec = FailInjectionSpec(kind=InjectionKind.TIMEOUT, error_message="boom")
    provider = MockProvider(spec=spec)
    with pytest.raises(TimeoutError):
        provider.evaluate("prompt")


def test_mock_tool_executor_inject_after_count():
    spec = FailInjectionSpec(kind=InjectionKind.TOOL, repeat_count=1)
    executor = MockToolExecutor(spec=spec)
    failed = executor(tool_name="web")
    assert failed["status"] == "error"
    ok = executor(tool_name="web")
    assert ok["status"] == "success"


def test_backoff_ms_positive():
    assert strategy_backoff_ms(0, base_ms=100) > 0
    assert strategy_backoff_ms(10, base_ms=100, max_ms=30000) <= 30000
