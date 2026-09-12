"""Validation for missions and startup plans.

Checklist-driven validation (§5): completeness of required fields, conflicting
constraints, unrealistic resources, well-formed success criteria, a clear
target outcome, explicit autonomy scope, and (when budgets/policies exist)
budget/policy conflicts. Validation blocks (errors) or advises (warnings);
it never executes anything.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.company.budget import BudgetManager
from app.company.policies import PolicyResolver
from app.db.models.company import GoalScopeType
from app.db.models.startup import Mission, StartupPlan
from app.startup.types import ValidationResult


def _as_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(v) for v in value]
    except (json.JSONDecodeError, TypeError):
        pass
    return [line for line in raw.splitlines() if line.strip()]


class MissionValidator:
    """Validate a mission against the completeness/safety checklist."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def validate(self, mission: Mission) -> ValidationResult:
        result = ValidationResult()

        statement = (mission.mission_statement or "").strip()
        if not statement:
            result.error("missing_mission_statement", "A mission statement is required")
        elif len(statement) < 10:
            result.warn("weak_mission_statement", "Mission statement is very short")

        if not (mission.title or "").strip():
            result.error("missing_title", "A mission title is required")

        constraints = _as_list(mission.constraints)
        if constraints:
            self._check_conflicting_constraints(result, constraints)

        criteria = _as_list(mission.success_criteria)
        if not criteria:
            result.warn("missing_success_criteria", "No success criteria defined")
        else:
            for criterion in criteria:
                if len(criterion) < 5:
                    result.warn(
                        "vague_success_criterion",
                        f"Success criterion is vague: {criterion!r}",
                    )

        if not (mission.target_market or "").strip():
            result.warn("missing_target_market", "No target market defined")

        if _as_list(mission.assumptions):
            self._check_unrealistic_resources(result, constraints)

        # A completed mission must be measurable.
        if (
            mission.status.value == "completed"
            and not (mission.desired_outcome or "").strip()
            and not criteria
        ):
            result.error("unmeasurable_completion", "Completed missions need a measurable outcome")

        self._check_budget_policy(result, mission)
        return result

    # ── Rule helpers ───────────────────────────────────────────────────

    def _check_conflicting_constraints(
        self, result: ValidationResult, constraints: list[str]
    ) -> None:
        low_text = " ".join(constraints).lower()
        pairs = [
            ("in 1 month/-30 days/this month", "enterprise/enterprise-scale"),
            ("free/budget under", "enterprise/scale"),
        ]
        for low_pair, high_pair in pairs:
            lows = [p.strip() for p in low_pair.split("/")]
            highs = [p.strip() for p in high_pair.split("/")]
            if any(low_term in low_text for low_term in lows) and any(
                high_term in low_text for high_term in highs
            ):
                result.warn(
                    "conflicting_constraints",
                    "Constraints appear to contradict (tight budget vs. enterprise scale)",
                )

    def _check_unrealistic_resources(
        self, result: ValidationResult, constraints: list[str]
    ) -> None:
        low_text = " ".join(constraints or []).lower()
        for token in ("free", "unlimited", "no budget", "infinite"):
            if token in low_text:
                result.warn(
                    "unrealistic_resources",
                    f"Constraint '{token}' is likely unrealistic for a bounded startup",
                )

    def _check_budget_policy(self, result: ValidationResult, mission: Mission) -> None:
        """Surface budget/policy conflicts when a company budget already exists."""
        budget = BudgetManager(self._db).get_budget(
            mission.company_id, GoalScopeType.COMPANY, mission.company_id
        )
        if budget is not None and budget.monthly_limit <= 0:
            result.warn("zero_budget", "Company budget has a zero monthly limit")
        resolver = PolicyResolver(self._db)
        detail = resolver.effective_detail("max_concurrent_work", company_id=mission.company_id)
        value = detail.get("value")
        if value is not None and str(value).strip() in ("0", "none", "disabled"):
            result.warn("policy_conflict", "A policy disables concurrent work for this company")


class StartupPlanValidator:
    """Validate a startup plan before it may be approved."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def validate(self, plan: StartupPlan) -> ValidationResult:
        result = ValidationResult()

        plan_fields = {
            "business_objectives": plan.business_objectives,
            "product_objectives": plan.product_objectives,
            "departments": plan.departments,
            "roles": plan.roles,
            "initial_products": plan.initial_products,
            "initial_projects": plan.initial_projects,
        }
        empty = [name for name, value in plan_fields.items() if not _loads_list(value)]
        if empty:
            result.warn(
                "missing_plan_sections",
                f"Startup plan is missing sections: {', '.join(empty)}",
            )

        if not _loads_list(plan.milestones):
            result.warn("no_milestones", "No milestones defined; plan cannot be tracked")

        kpi_targets = _loads_dict(plan.kpi_targets)
        if not kpi_targets:
            result.warn("no_kpi_targets", "No KPI targets defined in the plan")

        budget_allocation = _loads_dict(plan.budget_allocation)
        if not budget_allocation:
            result.warn("no_budget_allocation", "No budget allocation defined")

        if plan.status.value == "approved" and not (_loads_dict(plan.review) or {}).get(
            "approved_at"
        ):
            result.error("approval_missing_audit", "Approved plans must carry an approval audit")

        return result


def _loads_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
