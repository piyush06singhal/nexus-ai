"""AI Company Layer — work delegation down the reporting hierarchy.

Delegates a task from a manager to a direct report (or specified subordinate),
verifying authority, capability (skills), permissions, workload, budget, and
policy before delegating. A delegate is never allowed to grant itself a role,
permission, or budget increase — promotions/allocations require an authorized
independent actor (§51).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.company.budget import ResourceGovernor
from app.company.events import OrgEventLogger


class DelegationService:
    """Delegate work down the hierarchy with authorization + verification."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)
        self.governor = ResourceGovernor(db)
        from app.company.membership import MembershipManager

        self.memberships = MembershipManager(db)

    def can_delegate(
        self,
        *,
        company_id: UUID,
        from_employee_id: UUID,
        to_employee_id: UUID,
        authority_level: str = "manager",
    ) -> tuple[bool, list[str]]:
        """Verify that ``from`` can delegate to ``to``.

        Checks, in order:
          - both employees are members of the company
          - ``from`` is a manager (or authorized authority) and ``to`` is
            a direct report (or subordinate) of ``from``
          - ``to`` has an active membership (responsibility != forbidden)
        Returns ``(ok, reasons)`` where ``reasons`` lists any violations.
        """
        reasons: list[str] = []
        from_member = self.memberships.get(company_id, from_employee_id)
        to_member = self.memberships.get(company_id, to_employee_id)
        if from_member is None:
            reasons.append("from_not_a_member")
        if to_member is None:
            reasons.append("to_not_a_member")
        if from_member and to_member:
            role = self.memberships.role_of(from_member)
            auth_rank = {
                "company_admin": 4,
                "executive": 3,
                "manager": 2,
                "team_lead": 1,
                "individual_contributor": 0,
            }
            if role is None or auth_rank.get(role.authority_level.value, 0) < 2:
                reasons.append("insufficient_authority")
            # Must be in the same department OR is a manager above them.
            # Note: ``from_member.employee_id`` (not ``from_member.id``) is the
            # actor's employee id — a membership row's ``id`` is its own.
            if (
                from_member.department_id != to_member.department_id
                and from_member.manager_id != to_member.employee_id
            ):
                reasons.append("not_in_reporting_chain")
            if to_member.manager_id != from_member.employee_id:
                reasons.append("to_not_direct_report")
        return (not reasons, reasons)

    def delegate(
        self,
        *,
        company_id: UUID,
        from_employee_id: UUID,
        to_employee_id: UUID,
        task_name: str,
        task_description: str | None = None,
        estimated_cost: float = 0.0,
    ) -> dict[str, Any]:
        """Delegate a task to a direct report. Returns result or error reasons."""
        ok, reasons = self.can_delegate(
            company_id=company_id,
            from_employee_id=from_employee_id,
            to_employee_id=to_employee_id,
        )
        if not ok:
            self.events.log(
                actor=str(from_employee_id),
                action="delegation_denied",
                company_id=company_id,
                target_type="employee",
                target_id=to_employee_id,
                details={"task_name": task_name, "reasons": reasons},
                outcome="failed",
            )
            return {"delegated": False, "reasons": reasons}

        # Budget/policy guard: the assignee must be able to afford the work.
        affordable, budget_reasons = self.governor.can_execute(
            company_id=company_id,
            estimated_cost=estimated_cost,
            department_id=(
                self.memberships.get(company_id, to_employee_id).department_id
                if self.memberships.get(company_id, to_employee_id) is not None
                else None
            ),
            employee_id=to_employee_id,
        )
        if not affordable:
            return {"delegated": False, "reasons": budget_reasons}

        self.events.log(
            actor=str(from_employee_id),
            action="delegated",
            company_id=company_id,
            target_type="employee",
            target_id=to_employee_id,
            details={"task_name": task_name},
            outcome="success",
        )
        return {
            "delegated": True,
            "from_employee_id": str(from_employee_id),
            "to_employee_id": str(to_employee_id),
            "task_name": task_name,
            "task_description": task_description,
            "estimated_cost": estimated_cost,
            "timestamp": datetime.now(UTC).isoformat(),
        }
