"""Escalation service (Phase 6, spec §24–§25).

Creates persistent ``escalations`` records for human-in-the-loop review.
An escalation can never be auto-approved by the agent itself (§25).
A human must approve/reject it via the API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.reliability import Escalation, EscalationState
from app.recovery.types import EscalationContext


class EscalationService:
    """Manages escalation lifecycle: create, approve, reject, list, get."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        context: EscalationContext,
    ) -> Escalation:
        """Create a new escalation record.

        Args:
            context: Escalation context with issue, category, severity, etc.

        Returns:
            The persisted :class:`Escalation` row.
        """
        import json

        escalation = Escalation(
            id=uuid4(),
            execution_id=context.execution_id,
            orchestration_id=context.orchestration_id,
            workflow_id=context.workflow_id,
            issue=context.issue,
            category=context.category,
            severity=context.severity,
            state=EscalationState.PENDING_HUMAN_REVIEW,
            context=json.dumps(context.context_data, default=str) if context.context_data else None,
        )
        self.db.add(escalation)
        self.db.flush()
        return escalation

    def approve(
        self,
        escalation_id: UUID,
        decision_reason: str | None = None,
    ) -> Escalation | None:
        """Approve an escalation (human decision)."""
        escalation = self.db.get(Escalation, escalation_id)
        if not escalation or escalation.state != EscalationState.PENDING_HUMAN_REVIEW:
            return None

        escalation.state = EscalationState.APPROVED
        escalation.decision_reason = decision_reason
        escalation.reviewed_at = datetime.now(UTC)
        self.db.flush()
        return escalation

    def reject(
        self,
        escalation_id: UUID,
        decision_reason: str | None = None,
    ) -> Escalation | None:
        """Reject an escalation (human decision)."""
        escalation = self.db.get(Escalation, escalation_id)
        if not escalation or escalation.state != EscalationState.PENDING_HUMAN_REVIEW:
            return None

        escalation.state = EscalationState.REJECTED
        escalation.decision_reason = decision_reason
        escalation.reviewed_at = datetime.now(UTC)
        self.db.flush()
        return escalation

    def get(self, escalation_id: UUID) -> Escalation | None:
        """Get an escalation by ID."""
        return self.db.get(Escalation, escalation_id)

    def list_escalations(
        self,
        state: str | None = None,
        limit: int = 50,
    ) -> list[Escalation]:
        """List escalations, optionally filtered by state."""
        stmt = select(Escalation)
        if state:
            stmt = stmt.where(Escalation.state == EscalationState(state))
        stmt = stmt.order_by(Escalation.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def pending_count(self) -> int:
        """Count of pending human reviews."""
        stmt = select(Escalation).where(Escalation.state == EscalationState.PENDING_HUMAN_REVIEW)
        return len(list(self.db.execute(stmt).scalars().all()))


def escalation_to_dict(esc: Escalation) -> dict:
    """Serialize an Escalation row to a dict."""
    import json

    context_data = None
    if esc.context:
        try:
            context_data = json.loads(esc.context)
        except (json.JSONDecodeError, TypeError):
            context_data = esc.context

    return {
        "id": str(esc.id),
        "execution_id": str(esc.execution_id) if esc.execution_id else None,
        "orchestration_id": str(esc.orchestration_id) if esc.orchestration_id else None,
        "workflow_id": str(esc.workflow_id) if esc.workflow_id else None,
        "issue": esc.issue,
        "category": esc.category.value if esc.category else "unknown",
        "severity": esc.severity.value if esc.severity else "medium",
        "state": esc.state.value,
        "context": context_data,
        "decision_reason": esc.decision_reason,
        "reviewed_at": esc.reviewed_at,
        "created_at": esc.created_at,
    }
