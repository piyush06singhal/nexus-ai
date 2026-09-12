"""Strategic decisions — propose, then route through the Phase 8 decision layer.

:class:`StrategicDecisionEngine` recognizes decision situations (reprioritize,
reallocate, pause a product/project, iterate, new project, reassign an employee,
workforce change, milestone adjustment) and produces a *non-executing*
:class:`DecisionProposal`. When the proposal is high risk or the autonomy policy
says the action requires a human, it is recorded as a Phase 8 ``DecisionManager``
row; the engine itself never executes the outcome.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.company.decisions import DecisionManager
from app.company.roles import AuthorityLevel
from app.startup.autonomy import AutonomyService
from app.startup.types import DecisionProposal

_HIGH_RISK_CATEGORIES = ("reprioritize", "reallocate", "new_project", "workforce")


class StrategicDecisionEngine:
    """Recognize and propose strategic decisions under governance."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._decisions = DecisionManager(db)

    def propose(
        self,
        *,
        company_id: UUID,
        category: str,
        question: str,
        options: list[dict[str, Any]],
        rationale: str | None = None,
        evidence: dict[str, Any] | None = None,
        budget_impact: dict[str, Any] | None = None,
        requester_id: UUID | None = None,
    ) -> DecisionProposal:
        """Build a proposal, flagging when it must pass a human decision."""
        risk_level = _risk_for(category, budget_impact)
        requires_approval = risk_level in ("high", "critical") or not AutonomyService(
            self._db
        ).can_auto_act("replan", company_id)
        return DecisionProposal(
            category=category,
            question=question,
            options=options,
            rationale=rationale,
            risk_level=risk_level,
            evidence=evidence or {},
            budget_impact=budget_impact or {},
            requires_approval=requires_approval,
        )

    def submit(
        self,
        *,
        company_id: UUID,
        proposal: DecisionProposal,
        requester_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Record the proposal as a Phase 8 decision (non-executing)."""
        decision = self._decisions.create(
            company_id=company_id,
            question=proposal.question,
            options=proposal.options,
            requester_id=requester_id,
            context={"category": proposal.category, "source": "autonomous_startup_engine"},
            evidence=proposal.evidence,
            rationale=proposal.rationale,
            risk_level=proposal.risk_level,
            budget_impact=proposal.budget_impact,
            required_authority=_authority_for(proposal.risk_level),
        )
        return self._decisions.to_dict(decision)


def _risk_for(category: str, budget_impact: dict[str, Any] | None) -> str:
    amount = float((budget_impact or {}).get("amount", 0.0) or 0.0)
    if amount >= 1000:
        return "high"
    if category in _HIGH_RISK_CATEGORIES:
        return "high"
    if amount >= 250:
        return "medium"
    return "low"


def _authority_for(risk_level: str) -> AuthorityLevel:
    if risk_level in ("high", "critical"):
        return AuthorityLevel.EXECUTIVE
    if risk_level == "medium":
        return AuthorityLevel.MANAGER
    return AuthorityLevel.INDIVIDUAL_CONTRIBUTOR
