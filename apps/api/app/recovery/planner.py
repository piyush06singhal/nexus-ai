"""Recovery planner (Phase 6, spec §20–§21).

Given a diagnosis and policy, the planner chooses a recovery strategy via
:class:`RetrySafety` + budget checks, producing a :class:`RecoveryPlan`.

Strategy escalation path (spec §20):
    RETRY → RETRY_WITH_BACKOFF → RETRY_WITH_MODIFIED_INPUT → REPLAN →
    FALLBACK_AGENT → FALLBACK_TOOL → ESCALATE → ABORT

Each step consumes budget. When budget is exhausted, the planner escalates or
aborts. The planner preserves the original plan and writes a revised plan
without overwriting history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from app.recovery.budget import BudgetTracker, ExecutionBudget
from app.recovery.safety import RetrySafety
from app.recovery.strategy import RecoveryStrategy
from app.recovery.taxonomy import FailureCategory, FailureSeverity, max_auto_attempts
from app.recovery.types import FailureDiagnosis, RecoveryPlan

# ── Strategy escalation order ─────────────────────────────────────────────────

_STRATEGY_ESCALATION: list[RecoveryStrategy] = [
    RecoveryStrategy.RETRY,
    RecoveryStrategy.RETRY_WITH_BACKOFF,
    RecoveryStrategy.RETRY_WITH_MODIFIED_INPUT,
    RecoveryStrategy.REPLAN,
    RecoveryStrategy.FALLBACK_AGENT,
    RecoveryStrategy.FALLBACK_TOOL,
    RecoveryStrategy.ESCALATE,
    RecoveryStrategy.ABORT,
]


@dataclass
class RecoveryPlanner:
    """Plans recovery actions based on diagnosis, safety, and budget.

    Context:
        Uses :class:`RetrySafety` to evaluate safety of each strategy and
        :class:`BudgetTracker` to ensure we don't exceed recovery budgets.
    """

    safety: RetrySafety = field(default_factory=RetrySafety)
    budget: ExecutionBudget = field(default_factory=ExecutionBudget)
    max_attempts: int = 3

    def plan(
        self,
        diagnosis: FailureDiagnosis,
        previous_attempts: int = 0,
        original_plan: dict[str, Any] | None = None,
        execution_id: UUID | None = None,
        orchestration_id: UUID | None = None,
        workflow_id: UUID | None = None,
        context: dict[str, Any] | None = None,
    ) -> RecoveryPlan:
        """Produce a recovery plan for the given diagnosis.

        Args:
            diagnosis: Structured failure diagnosis.
            previous_attempts: How many recovery attempts have been made.
            original_plan: The original execution plan that failed.
            execution_id: Execution being recovered.
            orchestration_id: Orchestration being recovered.
            workflow_id: Workflow being recovered.
            context: Additional context for planning.

        Returns:
            A :class:`RecoveryPlan` with the chosen strategy and details.
        """
        tracker = BudgetTracker(self.budget)

        # Check budget
        if tracker.exhausted():
            return self._plan_abort(
                diagnosis,
                original_plan,
                execution_id,
                orchestration_id,
                workflow_id,
                reason=f"Budget exhausted: {tracker.exhausted_reason()}",
            )

        # Check max attempts
        if previous_attempts >= self.max_attempts:
            return self._plan_escalate_or_abort(
                diagnosis,
                previous_attempts,
                original_plan,
                execution_id,
                orchestration_id,
                workflow_id,
                reason=f"Max attempts ({self.max_attempts}) exceeded",
            )

        # Check severity → critical always escalates
        if FailureSeverity(diagnosis.severity) == FailureSeverity.CRITICAL:
            return self._plan_escalate(
                diagnosis,
                original_plan,
                execution_id,
                orchestration_id,
                workflow_id,
                reason="Critical severity — requires human intervention",
            )

        # Check if retryable
        if not diagnosis.retryable:
            return self._plan_escalate_or_abort(
                diagnosis,
                previous_attempts,
                original_plan,
                execution_id,
                orchestration_id,
                workflow_id,
                reason=f"Failure category '{diagnosis.category}' is not retryable",
            )

        # Choose strategy based on attempt count and safety
        strategy = self._choose_strategy(diagnosis, previous_attempts, context)

        # Verify safety
        tool_name = context.get("tool_name") if context else None
        tool_result_status = context.get("tool_result_status") if context else None

        safety_verdict = self.safety.evaluate(
            tool_name=tool_name,
            tool_result_status=tool_result_status,
            previous_attempts=previous_attempts,
        )

        if not safety_verdict.safe_to_retry:
            return self._plan_escalate(
                diagnosis,
                original_plan,
                execution_id,
                orchestration_id,
                workflow_id,
                reason=f"Safety check failed: {safety_verdict.reason}",
                safety_check=safety_verdict.to_dict(),
            )

        # Compute budget remaining
        budget_remaining = self.budget.max_retries - previous_attempts
        if budget_remaining <= 0:
            return self._plan_escalate_or_abort(
                diagnosis,
                previous_attempts,
                original_plan,
                execution_id,
                orchestration_id,
                workflow_id,
                reason="Retry budget exhausted",
            )

        return RecoveryPlan(
            request_id=uuid4(),
            execution_id=execution_id,
            orchestration_id=orchestration_id,
            workflow_id=workflow_id,
            category=diagnosis.category,
            severity=diagnosis.severity,
            strategy=strategy,
            original_plan=original_plan,
            revised_plan=self._build_revised_plan(original_plan, strategy, diagnosis),
            reason=diagnosis.root_cause,
            affected_tasks=[],
            safety_check=safety_verdict.to_dict(),
            budget_remaining=budget_remaining,
            escalate_after=max_auto_attempts(FailureSeverity(diagnosis.severity)),
        )

    def _choose_strategy(
        self,
        diagnosis: FailureDiagnosis,
        attempt: int,
        context: dict[str, Any] | None = None,
    ) -> RecoveryStrategy:
        """Choose the strategy based on attempt number and diagnosis.

        Follows the escalation path: each attempt escalates to a more
        aggressive strategy.
        """
        category = FailureCategory(diagnosis.category)

        # Category-specific first-choice strategies
        _CATEGORY_FIRST_CHOICE: dict[FailureCategory, RecoveryStrategy] = {
            FailureCategory.TIMEOUT: RecoveryStrategy.RETRY_WITH_BACKOFF,
            FailureCategory.MODEL_FAILURE: RecoveryStrategy.RETRY_WITH_MODIFIED_INPUT,
            FailureCategory.TOOL_FAILURE: RecoveryStrategy.FALLBACK_TOOL,
            FailureCategory.COMMUNICATION_FAILURE: RecoveryStrategy.RETRY_WITH_BACKOFF,
            FailureCategory.VALIDATION_FAILURE: RecoveryStrategy.RETRY_WITH_MODIFIED_INPUT,
            FailureCategory.INVALID_INPUT: RecoveryStrategy.RETRY_WITH_MODIFIED_INPUT,
            FailureCategory.INVALID_OUTPUT: RecoveryStrategy.RETRY_WITH_MODIFIED_INPUT,
        }

        first_choice = _CATEGORY_FIRST_CHOICE.get(category)
        if first_choice and attempt == 0:
            return first_choice

        # Escalation: pick from the escalation list based on attempt number
        idx = min(attempt, len(_STRATEGY_ESCALATION) - 2)  # -2 to leave room for ESCALATE/ABORT
        return _STRATEGY_ESCALATION[idx]

    def _build_revised_plan(
        self,
        original_plan: dict[str, Any] | None,
        strategy: RecoveryStrategy,
        diagnosis: FailureDiagnosis,
    ) -> dict[str, Any]:
        """Build a revised plan based on the chosen strategy."""
        return {
            "original": original_plan,
            "strategy": strategy.value,
            "diagnosis": {
                "category": diagnosis.category,
                "severity": diagnosis.severity,
                "root_cause": diagnosis.root_cause,
            },
            "modifications": self._strategy_modifications(strategy),
        }

    def _strategy_modifications(self, strategy: RecoveryStrategy) -> dict[str, Any]:
        """Strategy-specific modifications to the plan."""
        if strategy == RecoveryStrategy.RETRY_WITH_BACKOFF:
            return {"backoff_ms": 1000, "max_backoff_ms": 30000}
        if strategy == RecoveryStrategy.RETRY_WITH_MODIFIED_INPUT:
            return {"simplify_prompt": True, "add_examples": True}
        if strategy == RecoveryStrategy.REPLAN:
            return {"replan": True, "use_deterministic_planner": True}
        if strategy in (RecoveryStrategy.FALLBACK_AGENT, RecoveryStrategy.FALLBACK_TOOL):
            return {"use_fallback": True}
        return {}

    def _plan_abort(
        self,
        diagnosis: FailureDiagnosis,
        original_plan: dict[str, Any] | None,
        execution_id: UUID | None,
        orchestration_id: UUID | None,
        workflow_id: UUID | None,
        reason: str,
    ) -> RecoveryPlan:
        return RecoveryPlan(
            execution_id=execution_id,
            orchestration_id=orchestration_id,
            workflow_id=workflow_id,
            category=diagnosis.category,
            severity=diagnosis.severity,
            strategy=RecoveryStrategy.ABORT,
            original_plan=original_plan,
            reason=reason,
            budget_remaining=0,
        )

    def _plan_escalate(
        self,
        diagnosis: FailureDiagnosis,
        original_plan: dict[str, Any] | None,
        execution_id: UUID | None,
        orchestration_id: UUID | None,
        workflow_id: UUID | None,
        reason: str,
        safety_check: dict | None = None,
    ) -> RecoveryPlan:
        return RecoveryPlan(
            execution_id=execution_id,
            orchestration_id=orchestration_id,
            workflow_id=workflow_id,
            category=diagnosis.category,
            severity=diagnosis.severity,
            strategy=RecoveryStrategy.ESCALATE,
            original_plan=original_plan,
            reason=reason,
            safety_check=safety_check,
            budget_remaining=0,
        )

    def _plan_escalate_or_abort(
        self,
        diagnosis: FailureDiagnosis,
        previous_attempts: int,
        original_plan: dict[str, Any] | None,
        execution_id: UUID | None,
        orchestration_id: UUID | None,
        workflow_id: UUID | None,
        reason: str,
    ) -> RecoveryPlan:
        severity = FailureSeverity(diagnosis.severity)
        if severity in (FailureSeverity.HIGH, FailureSeverity.CRITICAL):
            return self._plan_escalate(
                diagnosis,
                original_plan,
                execution_id,
                orchestration_id,
                workflow_id,
                reason,
            )
        return self._plan_abort(
            diagnosis,
            original_plan,
            execution_id,
            orchestration_id,
            workflow_id,
            reason,
        )
