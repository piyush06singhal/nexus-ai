"""AI Company Layer — decision service.

Structured decision requests (question, options, evidence, risk, budget impact,
required authority) that flow through an explicit lifecycle and are reviewed by
authorized employees/humans. Only concise rationale + supporting evidence are
stored — never private chain-of-thought. Every lifecycle-changing operation is
authorization-controlled and auditable via ``decision_reviews`` + the event log.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger
from app.company.lifecycle import (
    CompanyLifecycleError,
    validate_decision_transition,
)
from app.company.membership import MembershipManager
from app.db.models.company import (
    AuthorityLevel,
    Decision,
    DecisionReview,
    DecisionStatus,
    DecisionVerdict,
)
from app.db.models.employee import AIEmployee

_AUTHORITY_RANK = {
    AuthorityLevel.INDIVIDUAL_CONTRIBUTOR: 0,
    AuthorityLevel.TEAM_LEAD: 1,
    AuthorityLevel.MANAGER: 2,
    AuthorityLevel.EXECUTIVE: 3,
    AuthorityLevel.COMPANY_ADMIN: 4,
}


class DecisionManager:
    """Create, review, approve, reject, and implement decisions."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)
        self.memberships = MembershipManager(db)

    def create(
        self,
        *,
        company_id: UUID,
        question: str,
        options: list[dict[str, Any]],
        requester_id: UUID | None = None,
        context: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        rationale: str | None = None,
        risk_level: str = "low",
        risk: dict[str, Any] | None = None,
        budget_impact: dict[str, Any] | None = None,
        required_authority: AuthorityLevel = AuthorityLevel.EXECUTIVE,
    ) -> Decision:
        """Create a decision request in ``draft`` status."""
        decision = Decision(
            company_id=company_id,
            requester_id=requester_id,
            question=question,
            options=json.dumps(options),
            context=json.dumps(context) if context else None,
            evidence=json.dumps(evidence) if evidence else None,
            rationale=rationale,
            risk_level=risk_level,
            risk=json.dumps(risk) if risk else None,
            budget_impact=json.dumps(budget_impact) if budget_impact else None,
            required_authority=required_authority,
            status=DecisionStatus.DRAFT,
        )
        self._db.add(decision)
        self._db.flush()
        self._record_review(
            decision,
            action="created",
            reviewer_id=requester_id,
            rationale="Decision created",
        )
        self.events.log(
            actor=self._actor(requester_id),
            action="decision_created",
            company_id=company_id,
            target_type="decision",
            target_id=decision.id,
            details={"question": question, "risk_level": risk_level},
            outcome="success",
        )
        self._db.commit()
        return decision

    def get(self, decision_id: UUID) -> Decision | None:
        return self._db.get(Decision, decision_id)

    def _require(self, decision_id: UUID) -> Decision:
        decision = self._db.get(Decision, decision_id)
        if decision is None:
            raise ValueError(f"Decision {decision_id} not found")
        return decision

    def list_(self, company_id: UUID, *, status: DecisionStatus | None = None) -> list[Decision]:
        stmt = (
            select(Decision)
            .where(Decision.company_id == company_id)
            .order_by(Decision.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(Decision.status == status)
        return list(self._db.execute(stmt).scalars().all())

    # ── Lifecycle ─────────────────────────────────────────────────────

    def submit(self, decision_id: UUID, *, actor_id: UUID | None = None) -> Decision:
        """Move a draft decision to ``pending_review`` (draft → pending_review)."""
        decision = self._require(decision_id)
        validate_decision_transition(decision.status, DecisionStatus.PENDING_REVIEW)
        decision.status = DecisionStatus.PENDING_REVIEW
        decision.decision_maker_id = actor_id
        self._db.flush()
        self._record_review(decision, "submitted", actor_id, "Submitted for review")
        self._log(decision, "decision_submitted", actor_id)
        self._db.commit()
        return decision

    def approve(self, decision_id: UUID, *, reviewer_id: UUID, rationale: str) -> Decision:
        """Approve a pending decision (pending_review → approved)."""
        decision = self._require(decision_id)
        self._authorize(reviewer_id, decision.company_id, decision.required_authority)
        validate_decision_transition(decision.status, DecisionStatus.APPROVED)
        decision.status = DecisionStatus.APPROVED
        decision.decision_maker_id = reviewer_id
        self._db.flush()
        self._record_review(
            decision, "approved", reviewer_id, rationale, verdict=DecisionVerdict.APPROVE
        )
        self._log(decision, "decision_approved", reviewer_id)
        self._db.commit()
        return decision

    def reject(self, decision_id: UUID, *, reviewer_id: UUID, rationale: str) -> Decision:
        """Reject a pending decision (pending_review → rejected)."""
        decision = self._require(decision_id)
        self._authorize(reviewer_id, decision.company_id, decision.required_authority)
        validate_decision_transition(decision.status, DecisionStatus.REJECTED)
        decision.status = DecisionStatus.REJECTED
        decision.decision_maker_id = reviewer_id
        self._db.flush()
        self._record_review(
            decision, "rejected", reviewer_id, rationale, verdict=DecisionVerdict.REJECT
        )
        self._log(decision, "decision_rejected", reviewer_id)
        self._db.commit()
        return decision

    def implement(self, decision_id: UUID, *, actor_id: UUID) -> Decision:
        """Implement an approved decision (approved → implemented)."""
        decision = self._require(decision_id)
        validate_decision_transition(decision.status, DecisionStatus.IMPLEMENTED)
        decision.status = DecisionStatus.IMPLEMENTED
        self._db.flush()
        self._record_review(decision, "implemented", actor_id, "Decision implemented")
        self._log(decision, "decision_implemented", actor_id)
        self._db.commit()
        return decision

    # ── Authorization / helpers ───────────────────────────────────────

    def _authorize(self, reviewer_id: UUID, company_id: UUID, required: AuthorityLevel) -> None:
        """Enforce that the reviewer's role authority meets the requirement."""
        membership = self.memberships.get(company_id, reviewer_id)
        if membership is None:
            raise ValueError("Reviewer is not a member of this company")
        role = self.memberships.role_of(membership)
        if role is None:
            raise CompanyLifecycleError("no-role", required.value, entity="authority")
        granted = _AUTHORITY_RANK.get(role.authority_level, 0)
        needed = _AUTHORITY_RANK.get(required, 0)
        if granted < needed:
            raise CompanyLifecycleError(
                role.authority_level.value,
                required.value,
                entity="authority (insufficient)",
            )
        return role.authority_level

    def _record_review(
        self,
        decision: Decision,
        action: str,
        reviewer_id: UUID | None,
        rationale: str | None,
        verdict: DecisionVerdict | None = None,
    ) -> DecisionReview:
        previous = decision.status.value
        review = DecisionReview(
            decision_id=decision.id,
            reviewer_id=reviewer_id,
            action=action,
            verdict=verdict,
            rationale=rationale,
            previous_status=previous,
        )
        self._db.add(review)
        self._db.flush()
        # Set next_status after flush (status unchanged on the model here).
        review.next_status = decision.status.value
        return review

    def _log(self, decision: Decision, action: str, actor_id: UUID | None) -> None:
        self.events.log(
            actor=self._actor(actor_id),
            action=action,
            company_id=decision.company_id,
            target_type="decision",
            target_id=decision.id,
            details={"question": decision.question, "status": decision.status.value},
            outcome="success",
        )

    def _actor(self, employee_id: UUID | None) -> str:
        if employee_id is None:
            return "system"
        emp = self._db.get(AIEmployee, employee_id)
        return (emp and (emp.display_name or emp.name)) or str(employee_id)

    def reviews(self, decision_id: UUID) -> list[DecisionReview]:
        stmt = (
            select(DecisionReview)
            .where(DecisionReview.decision_id == decision_id)
            .order_by(DecisionReview.created_at)
        )
        return list(self._db.execute(stmt).scalars().all())

    def to_dict(self, decision: Decision) -> dict[str, Any]:
        return {
            "id": str(decision.id),
            "company_id": str(decision.company_id),
            "requester_id": str(decision.requester_id) if decision.requester_id else None,
            "decision_maker_id": (
                str(decision.decision_maker_id) if decision.decision_maker_id else None
            ),
            "question": decision.question,
            "context": json.loads(decision.context) if decision.context else None,
            "options": json.loads(decision.options),
            "selected_option": (
                json.loads(decision.selected_option) if decision.selected_option else None
            ),
            "evidence": json.loads(decision.evidence) if decision.evidence else None,
            "rationale": decision.rationale,
            "risk_level": decision.risk_level,
            "risk": json.loads(decision.risk) if decision.risk else None,
            "budget_impact": (
                json.loads(decision.budget_impact) if decision.budget_impact else None
            ),
            "required_authority": decision.required_authority.value,
            "status": decision.status.value,
            "created_at": decision.created_at.isoformat() if decision.created_at else None,
            "updated_at": decision.updated_at.isoformat() if decision.updated_at else None,
        }
