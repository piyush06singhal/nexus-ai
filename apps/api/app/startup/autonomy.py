"""Bounded autonomy — the governance gate every autonomous action passes.

Every autonomous action in the startup engine is evaluated against the
company's :class:`AutonomyPolicy` (one row per company) plus the global
``MAX_*`` limits: the policy decides whether the action runs automatically,
must pass a human approval gate, or is blocked outright. It is the single
chokepoint consulted by the operating cycle, the employee provisioner, product
launch, budget changes, and replanning — no skip-paths.

Action decisions are prescriptive (:class:`ActionDecision`):
- ``allow`` — may run automatically (subject to budget/policy limits).
- ``require_approval`` — must first get an approved ``approval_gates`` row.
- ``block`` — never autonomous for this company, ever.

``change_autonomy`` is never automatic, and a hard-coded set of actions
(finance, legal, human hire/fire, external publish, self-modification) are
always blocked — bounded autonomy is structural, not negotiable.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.budget import BudgetManager
from app.core.config import settings
from app.db.models.company import GoalScopeType
from app.db.models.startup import ApprovalGate, AutonomyLevel, AutonomyPolicy
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.types import ActionDecision

# Actions the engine may consult the matrix for.
ACTION_EXECUTE_TASK = "execute_task"
ACTION_CREATE_GOAL = "create_goal"
ACTION_RECORD_KPI = "record_kpi"
ACTION_CREATE_PRODUCT = "create_product"
ACTION_ACTIVATE_PROJECT = "activate_project"
ACTION_ALLOCATE_BUDGET = "allocate_budget"
ACTION_RUN_CYCLE = "run_cycle"
ACTION_LAUNCH_PRODUCT = "launch_product"
ACTION_REPLAN = "replan"
ACTION_PROVISION_EMPLOYEE = "provision_employee"
ACTION_CHANGE_AUTONOMY = "change_autonomy"

# Never autonomous, at any level — structural safety boundary.
_NEVER_ALLOWED: frozenset[str] = frozenset(
    {
        "finance",
        "legal",
        "hire_human",
        "fire_employee",
        "external_publish",
        "external_integration",
        "browser_automation",
        "computer_use",
        "self_modify",
        "self_rewrite",
        "simulation_platform",
        "production_deploy",
        "payment_processing",
        "create_external_account",
        "unlimited_budget",
    }
)

# Never automatic, must always go through a human approval gate.
_ALWAYS_REQUIRE_APPROVAL: frozenset[str] = frozenset({ACTION_CHANGE_AUTONOMY})

_DEFAULT_MATRICES: dict[AutonomyLevel, dict[str, str]] = {
    AutonomyLevel.MANUAL: {},
    AutonomyLevel.ASSISTED: {
        ACTION_EXECUTE_TASK: "allow",
        ACTION_CREATE_GOAL: "allow",
        ACTION_ACTIVATE_PROJECT: "allow",
    },
    AutonomyLevel.BOUNDED_AUTONOMY: {
        ACTION_EXECUTE_TASK: "allow",
        ACTION_CREATE_GOAL: "allow",
        ACTION_RECORD_KPI: "allow",
        ACTION_ACTIVATE_PROJECT: "allow",
        ACTION_CREATE_PRODUCT: "allow",
        ACTION_RUN_CYCLE: "allow",
    },
    AutonomyLevel.HIGH_AUTONOMY: {
        ACTION_EXECUTE_TASK: "allow",
        ACTION_CREATE_GOAL: "allow",
        ACTION_RECORD_KPI: "allow",
        ACTION_ALLOCATE_BUDGET: "allow",
        ACTION_ACTIVATE_PROJECT: "allow",
        ACTION_CREATE_PRODUCT: "allow",
        ACTION_RUN_CYCLE: "allow",
        ACTION_LAUNCH_PRODUCT: "allow",
        ACTION_REPLAN: "allow",
        ACTION_PROVISION_EMPLOYEE: "allow",
    },
}

_DEFAULT_REQUIRE_APPROVAL: dict[AutonomyLevel, list[str]] = {
    AutonomyLevel.MANUAL: list(_NEVER_ALLOWED),
    AutonomyLevel.ASSISTED: [
        ACTION_RECORD_KPI,
        ACTION_ALLOCATE_BUDGET,
        ACTION_CREATE_PRODUCT,
        ACTION_RUN_CYCLE,
        ACTION_LAUNCH_PRODUCT,
        ACTION_REPLAN,
        ACTION_PROVISION_EMPLOYEE,
    ],
    AutonomyLevel.BOUNDED_AUTONOMY: [
        ACTION_LAUNCH_PRODUCT,
        ACTION_REPLAN,
        ACTION_PROVISION_EMPLOYEE,
        ACTION_ALLOCATE_BUDGET,
    ],
    AutonomyLevel.HIGH_AUTONOMY: [ACTION_CHANGE_AUTONOMY],
}


class AutonomyService:
    """Evaluate and administer per-company autonomy governance."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    # ── Policy CRUD ────────────────────────────────────────────────────

    def get_policy(self, company_id: UUID) -> AutonomyPolicy:
        """Return the company's autonomy policy, materializing a default."""
        policy = self._db.scalar(
            select(AutonomyPolicy).where(AutonomyPolicy.company_id == company_id)
        )
        if policy is not None:
            return policy
        level = AutonomyLevel(settings.startup_default_autonomy_level)
        policy = AutonomyPolicy(
            company_id=company_id,
            autonomy_level=level,
            allow_matrix="{}",
            max_employees=settings.startup_max_employees,
            max_departments=None,
            max_budget=settings.startup_max_budget,
            max_concurrent_work=settings.startup_max_concurrent_operations,
            max_provisioning_rate=None,
            require_approval_for=json.dumps(_DEFAULT_REQUIRE_APPROVAL.get(level, [])),
        )
        self._db.add(policy)
        self._db.commit()
        return policy

    def set_policy(
        self,
        company_id: UUID,
        *,
        autonomy_level: AutonomyLevel | str | None = None,
        allow_matrix: dict[str, str] | None = None,
        max_employees: int | None = None,
        max_departments: int | None = None,
        max_budget: float | None = None,
        max_concurrent_work: int | None = None,
        max_provisioning_rate: int | None = None,
        require_approval_for: list[str] | None = None,
        actor: str = "system",
    ) -> AutonomyPolicy:
        """Update a company's autonomy policy (governed at the caller layer).

        Changing ``autonomy_level`` is ``change_autonomy`` — it is never
        automatic; the caller is expected to have an approved gate. This method
        only records the update and an audit event.
        """
        policy = self.get_policy(company_id)
        if autonomy_level is not None:
            policy.autonomy_level = AutonomyLevel(autonomy_level)
        if allow_matrix is not None:
            policy.allow_matrix = json.dumps(allow_matrix)
        if max_employees is not None:
            policy.max_employees = max_employees
        if max_departments is not None:
            policy.max_departments = max_departments
        if max_budget is not None:
            policy.max_budget = max_budget
        if max_concurrent_work is not None:
            policy.max_concurrent_work = max_concurrent_work
        if max_provisioning_rate is not None:
            policy.max_provisioning_rate = max_provisioning_rate
        if require_approval_for is not None:
            policy.require_approval_for = json.dumps(require_approval_for)
        self._db.commit()
        self._events.log(
            action=StartupEvents.AUTONOMY_POLICY_UPDATED,
            company_id=company_id,
            actor=actor,
            target_type="autonomy_policy",
            target_id=policy.id,
            details={"autonomy_level": policy.autonomy_level.value},
            outcome="success",
        )
        return policy

    def to_dict(self, company_id: UUID) -> dict[str, Any]:
        policy = self.get_policy(company_id)
        return {
            "company_id": str(company_id),
            "autonomy_level": policy.autonomy_level.value,
            # Effective matrix: per-level defaults merged with any company
            # overrides — the verdicts the engine actually prescribes.
            "allow_matrix": self._effective_matrix(policy),
            "never_allowed": sorted(_NEVER_ALLOWED),
            "max_employees": policy.max_employees,
            "max_departments": policy.max_departments,
            "max_budget": policy.max_budget,
            "max_concurrent_work": policy.max_concurrent_work,
            "max_provisioning_rate": policy.max_provisioning_rate,
            "require_approval_for": _loads_list(policy.require_approval_for),
        }

    # ── Decision ───────────────────────────────────────────────────────

    def decision(
        self,
        action: str,
        company_id: UUID,
        *,
        estimated_cost: float = 0.0,
        actor: str = "system",
    ) -> tuple[ActionDecision, str]:
        """Return ``(ActionDecision, reason)`` for an autonomous action."""
        if action in _NEVER_ALLOWED:
            return (ActionDecision.BLOCK, f"Action '{action}' is never autonomous")
        policy = self.get_policy(company_id)
        level = policy.autonomy_level

        if action in _ALWAYS_REQUIRE_APPROVAL:
            return (
                ActionDecision.REQUIRE_APPROVAL,
                f"'{action}' always requires human approval",
            )

        matrix = self._effective_matrix(policy)
        require = self._require_approval(policy)
        if action in require:
            return (
                ActionDecision.REQUIRE_APPROVAL,
                f"'{action}' requires an approved approval gate for autonomy level {level.value}",
            )

        setting = matrix.get(action)
        if setting != "allow":
            # Unknown / unlisted actions at this level require a human.
            return (
                ActionDecision.REQUIRE_APPROVAL,
                f"'{action}' is not auto-allowed at autonomy level {level.value}",
            )
        if level == AutonomyLevel.MANUAL:
            return (
                ActionDecision.REQUIRE_APPROVAL,
                "Manual autonomy: every action requires human approval",
            )

        # Budget / resource limits refine an otherwise-allowed action.
        if estimated_cost > 0:
            effective = self._budget_cap(policy)
            if effective is not None and estimated_cost > effective:
                return (
                    ActionDecision.REQUIRE_APPROVAL,
                    f"Estimated cost {estimated_cost:.2f} exceeds cap {effective:.2f}",
                )
            budget = BudgetManager(self._db).get_budget(
                company_id, GoalScopeType.COMPANY, company_id
            )
            if budget is not None and estimated_cost > budget.monthly_limit:
                return (
                    ActionDecision.REQUIRE_APPROVAL,
                    f"Estimated cost {estimated_cost:.2f} exceeds the company "
                    f"monthly budget {budget.monthly_limit:.2f}",
                )

        return (ActionDecision.ALLOW, f"'{action}' is auto-allowed")

    def can_auto_act(self, action: str, company_id: UUID, *, estimated_cost: float = 0.0) -> bool:
        decision, _ = self.decision(action, company_id, estimated_cost=estimated_cost)
        return decision == ActionDecision.ALLOW

    def enforce(
        self,
        action: str,
        company_id: UUID,
        *,
        estimated_cost: float = 0.0,
        actor: str = "system",
        approved_gate_id: UUID | None = None,
    ) -> ActionDecision:
        """Enforce the decision for an action the engine wants to take.

        ``approved_gate_id`` may be supplied by the caller when the action was
        previously routed to an approval gate and that gate is now approved;
        otherwise a requiring/blocking action raises.
        """
        decision, reason = self.decision(
            action, company_id, estimated_cost=estimated_cost, actor=actor
        )
        if decision == ActionDecision.ALLOW:
            return ActionDecision.ALLOW
        if decision == ActionDecision.REQUIRE_APPROVAL:
            # An approved gate id by the caller satisfies the gate.
            if approved_gate_id is not None:
                gate = self._db.get(ApprovalGate, approved_gate_id)
                if (
                    gate is not None
                    and gate.company_id == company_id
                    and gate.status.value == "approved"
                ):
                    return ActionDecision.ALLOW
            message = f"'{action}' requires approval: {reason}"
            self._events.log(
                action=StartupEvents.ACTION_REQUIRES_APPROVAL,
                company_id=company_id,
                actor=actor,
                target_type="autonomy",
                details={"action": action, "reason": reason},
                outcome="warning",
            )
            from app.startup.types import ApprovalRequiredError

            raise ApprovalRequiredError(company_id, action, message)
        from app.startup.types import AutonomyBlockedError

        self._events.log(
            action=StartupEvents.AUTONOMY_BLOCKED,
            company_id=company_id,
            actor=actor,
            target_type="autonomy",
            details={"action": action, "reason": reason},
            outcome="blocked",
        )
        raise AutonomyBlockedError(company_id, action, reason)

    # ── Effective limits ───────────────────────────────────────────────

    def _effective_matrix(self, policy: AutonomyPolicy) -> dict[str, str]:
        merged = dict(_DEFAULT_MATRICES.get(policy.autonomy_level, {}))
        configured = _loads(policy.allow_matrix)
        if isinstance(configured, dict):
            merged.update({str(k): str(v) for k, v in configured.items()})
        return merged

    def _require_approval(self, policy: AutonomyPolicy) -> list[str]:
        return _loads_list(policy.require_approval_for)

    def _budget_cap(self, policy: AutonomyPolicy) -> float | None:
        caps = [c for c in (policy.max_budget, settings.startup_max_budget) if c is not None]
        return min(caps) if caps else None


def _loads(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _loads_list(raw: str | None) -> list[str]:
    value = _loads(raw)
    return [str(v) for v in value] if isinstance(value, list) else []
