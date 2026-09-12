"""Organizational blueprint — a configurable company structure.

Builds an :class:`BlueprintData` (departments → roles → authority → skills →
reporting → staffing → objectives → KPIs → budgets) for a startup plan. The
structure is driven by the plan's own ``departments``/``roles`` JSON when
present, otherwise derived from the mission's required capabilities. Never a
single hardcoded org chart.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.startup import OrganizationalBlueprint, StartupPlan
from app.startup.types import BlueprintData, BlueprintDepartment

_DEFAULT_AUTHORITY = {
    "executive": "company_admin",
    "head": "executive",
    "lead": "manager",
    "ic": "individual_contributor",
}


class BlueprintBuilder:
    """Build a configurable organizational blueprint."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def build(self, plan: StartupPlan) -> BlueprintData:
        configured = _as_list(plan.departments)
        if configured:
            departments = [
                BlueprintDepartment(
                    name=dept.get("name", "Unknown") if isinstance(dept, dict) else str(dept),
                    mission=(dept.get("mission") if isinstance(dept, dict) else None),
                    roles=_as_list(dept.get("roles") if isinstance(dept, dict) else None),
                    reports_to=(dept.get("reports_to") if isinstance(dept, dict) else None),
                )
                for dept in configured
            ]
        else:
            departments = self._derive_departments(plan)

        return BlueprintData(
            departments=departments,
            authority=_DEFAULT_AUTHORITY,
            kpis=self._kpis(plan),
            budgets=self._budgets(plan),
        )

    def persist(
        self,
        plan: StartupPlan,
        *,
        name: str = "Default blueprint",
        structure: BlueprintData | None = None,
    ) -> OrganizationalBlueprint:
        data = structure or self.build(plan)
        blueprint = OrganizationalBlueprint(
            startup_plan_id=plan.id,
            name=name,
            structure=json.dumps(data.to_dict(), default=str),
        )
        self._db.add(blueprint)
        self._db.commit()
        return blueprint

    # ── Derivation helpers ─────────────────────────────────────────────

    def _derive_departments(self, plan: StartupPlan) -> list[BlueprintDepartment]:
        """Map required capabilities to a sensible department set."""
        capabilities = _as_list(plan.capabilities)
        low = " ".join(capabilities).lower()
        departments: list[BlueprintDepartment] = []
        if "operating" in low or "operations" in low or not capabilities:
            departments.append(
                BlueprintDepartment(
                    name="Operations",
                    mission="Run and govern the startup's cycle operations",
                    roles=[self._ic_role("operations")],
                )
            )
        if any(token in low for token in ("engineering", "product", "platform", "sdk", "ai", "ml")):
            departments.insert(
                0,
                BlueprintDepartment(
                    name="Engineering",
                    mission="Build and maintain the core product",
                    roles=[self._ic_role("engineering")],
                    reports_to="Executive",
                ),
            )
        if "marketing" in low or "go-to-market" in low:
            departments.append(
                BlueprintDepartment(
                    name="Marketing",
                    mission="Reach and acquire the target market",
                    roles=[self._ic_role("marketing")],
                    reports_to="Executive",
                )
            )
        if "research" in low or "validation" in low:
            departments.append(
                BlueprintDepartment(
                    name="Research",
                    mission="Validate problem/solution fit with evidence",
                    roles=[self._ic_role("research")],
                    reports_to="Engineering",
                )
            )
        # Executive always exists to carry authority.
        departments.append(
            BlueprintDepartment(
                name="Executive",
                mission="Own the mission, strategy, and bounded-autonomy governance",
                roles=[self._exec_role()],
            )
        )
        return departments

    @staticmethod
    def _exec_role() -> dict[str, Any]:
        return {
            "name": "founder_ceo",
            "title": "Founder & CEO",
            "authority_level": "company_admin",
            "responsibilities": [
                "Own mission and strategy",
                "Approve high-risk autonomous actions",
            ],
            "required_skills": ["leadership", "strategy"],
        }

    @staticmethod
    def _ic_role(domain: str) -> dict[str, Any]:
        return {
            "name": f"{domain}_specialist",
            "title": f"{domain.title()} Specialist",
            "authority_level": "individual_contributor",
            "responsibilities": [f"Execute {domain} objectives"],
            "required_skills": [domain],
        }

    def _kpis(self, plan: StartupPlan) -> list[dict[str, Any]]:
        targets = _as_dict(plan.kpi_targets)
        kpis: list[dict[str, Any]] = []
        if targets:
            for name, target in targets.items():
                kpis.append({"name": name, "target": target, "category": "operational"})
        else:
            kpis = [
                {"name": "task_success_rate", "target": 0.9, "category": "reliability"},
                {"name": "execution_throughput", "target": 10, "category": "productivity"},
                {"name": "budget_utilization", "target": 0.8, "category": "cost"},
            ]
        return kpis

    def _budgets(self, plan: StartupPlan) -> dict[str, Any]:
        allocation = _as_dict(plan.budget_allocation)
        return allocation or {
            "company": None,
            "departments": {},
        }


def _as_list(raw) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw  # already parsed (e.g. a department's roles within a plan)
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _as_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
