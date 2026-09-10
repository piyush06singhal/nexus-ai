"""Recovery service (Phase 6).

Thin CRUD and lifecycle orchestration over the recovery package. Mirrors the
`OrchestrationService` pattern. Coordinates recovery execution, escalation,
and serialization for the API.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.recovery.engine import RecoveryEngine
from app.recovery.escalation import EscalationService


class RecoveryService:
    """Coordinates recovery operations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._engine = RecoveryEngine(db)
        self._escalation_service = EscalationService(db)

    # ── Recovery lifecycle ─────────────────────────────────────────────────────

    def recover(
        self,
        execution_id: UUID,
        *,
        error_text: str | None = None,
        exception_type: str | None = None,
        tool_call_status: str | None = None,
        tool_call_result: dict | None = None,
        original_plan: dict | None = None,
        context: dict | None = None,
    ):
        """Trigger the recovery engine for a failed execution."""
        return self._engine.recover(
            execution_id,
            error_text=error_text,
            exception_type=exception_type,
            tool_call_status=tool_call_status,
            tool_call_result=tool_call_result,
            original_plan=original_plan,
            context=context,
        )

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_attempt(self, attempt_id: UUID):
        return self._engine.get_attempt(attempt_id)

    def list_attempts_for_execution(self, execution_id: UUID):
        return self._engine.list_attempts_for_execution(execution_id)

    def get_plan(self, plan_id: UUID):
        return self._engine.get_plan(plan_id)

    def get_diagnosis(self, diagnosis_id: UUID):
        return self._engine.get_diagnosis(diagnosis_id)

    def diagnosis_for_execution(self, execution_id: UUID):
        """Get the most recent diagnosis for an execution."""
        from sqlalchemy import select

        from app.db.models.reliability import FailureDiagnosis

        stmt = (
            select(FailureDiagnosis)
            .where(FailureDiagnosis.execution_id == execution_id)
            .order_by(FailureDiagnosis.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def plan_for_execution(self, execution_id: UUID):
        """Get the most recent recovery plan for an execution."""
        from sqlalchemy import select

        from app.db.models.reliability import RecoveryPlan

        stmt = (
            select(RecoveryPlan)
            .where(RecoveryPlan.execution_id == execution_id)
            .order_by(RecoveryPlan.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    # ── Escalations ───────────────────────────────────────────────────────────

    def list_escalations(self, state: str | None = None, limit: int = 50):
        return self._escalation_service.list_escalations(state=state, limit=limit)

    def get_escalation(self, escalation_id: UUID):
        return self._escalation_service.get(escalation_id)

    def approve_escalation(self, escalation_id: UUID, decision_reason: str | None = None):
        return self._escalation_service.approve(escalation_id, decision_reason)

    def reject_escalation(self, escalation_id: UUID, decision_reason: str | None = None):
        return self._escalation_service.reject(escalation_id, decision_reason)

    def pending_escalation_count(self) -> int:
        return self._escalation_service.pending_count()


def attempt_to_dict(attempt) -> dict:
    """Serialize a recovery attempt to a dict."""
    from app.recovery.engine import RecoveryAttemptRow
    from app.recovery.types import RecoveryAttempt

    if isinstance(attempt, RecoveryAttempt):
        return attempt.to_dict()
    if isinstance(attempt, RecoveryAttemptRow):
        import json

        return {
            "id": str(attempt.id),
            "execution_id": str(attempt.execution_id) if attempt.execution_id else None,
            "plan_id": str(attempt.plan_id) if attempt.plan_id else None,
            "attempt_number": attempt.attempt_number,
            "state": attempt.state.value,
            "strategy": attempt.strategy,
            "verification_result_id": str(attempt.verification_result_id)
            if attempt.verification_result_id
            else None,
            "outcome": attempt.outcome,
            "reason": attempt.reason,
            "metadata": json.loads(attempt.metadata_json) if attempt.metadata_json else None,
            "started_at": attempt.started_at,
            "completed_at": attempt.completed_at,
            "created_at": attempt.created_at,
        }
    return None


def plan_to_dict(plan) -> dict:
    """Serialize a recovery plan to a dict."""
    import json

    return {
        "id": str(plan.id),
        "execution_id": str(plan.execution_id) if plan.execution_id else None,
        "orchestration_id": str(plan.orchestration_id) if plan.orchestration_id else None,
        "workflow_id": str(plan.workflow_id) if plan.workflow_id else None,
        "category": plan.category.value if plan.category else "unknown",
        "severity": plan.severity.value if plan.severity else "medium",
        "strategy": plan.strategy,
        "original_plan": json.loads(plan.original_plan) if plan.original_plan else None,
        "revised_plan": json.loads(plan.revised_plan) if plan.revised_plan else None,
        "reason": plan.reason,
        "affected_tasks": json.loads(plan.affected_tasks) if plan.affected_tasks else None,
        "safety_check": json.loads(plan.safety_check) if plan.safety_check else None,
        "created_at": plan.created_at,
    }


def diagnosis_to_dict(diag) -> dict:
    """Serialize a failure diagnosis to a dict."""
    import json

    return {
        "id": str(diag.id),
        "execution_id": str(diag.execution_id) if diag.execution_id else None,
        "category": diag.category.value if diag.category else "unknown",
        "severity": diag.severity.value if diag.severity else "medium",
        "root_cause": diag.root_cause,
        "retryable": diag.retryable,
        "recommended_strategy": diag.recommended_strategy,
        "confidence": diag.confidence,
        "evidence": json.loads(diag.evidence) if diag.evidence else None,
        "created_at": diag.created_at,
    }
