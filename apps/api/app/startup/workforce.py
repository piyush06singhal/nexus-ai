"""Workforce planning — map a blueprint to concrete staffing demand.

Translate an organizational blueprint (departments, roles) into a list of
:class:`WorkforceDemand` entries (role, department, count, skills, priority,
workload, monthly budget, authority) while enforcing the configured
``MAX_AUTONOMOUS_EMPLOYEES`` cap. Planning is a proposal — provisioning still
runs through :class:`EmployeeProvisioner` with autonomy gates.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.company.roles import RoleManager
from app.core.config import settings
from app.db.models.startup import StartupPlan, WorkforcePlan
from app.startup.blueprint import BlueprintBuilder
from app.startup.types import BlueprintData, WorkforceDemand

_DEFAULT_WORKLOAD = {
    "capacity": settings.employee_default_capacity,
    "max_concurrent_tasks": settings.employee_max_concurrent_tasks,
}


class WorkforcePlanner:
    """Plan workforce demand from a startup plan's blueprint."""

    def __init__(self, db: Session) -> None:
        self._db = db

    @property
    def max_employees(self) -> int:
        return settings.startup_max_employees

    def plan(
        self, plan: StartupPlan, blueprint: BlueprintData | None = None
    ) -> list[WorkforceDemand]:
        data = blueprint or BlueprintBuilder(self._db).build(plan)
        demand: list[WorkforceDemand] = []
        existing_roles = _existing_role_names(self._db, plan.mission.company_id)

        for dept in data.departments:
            for role in dept.roles:
                role_name = role.get("name", "employee")
                authority = role.get("authority_level", "individual_contributor")
                demand.append(
                    WorkforceDemand(
                        role=role_name,
                        department=dept.name,
                        count=1,
                        skills=role.get("required_skills", []) or [],
                        priority=(100 if authority == "company_admin" else 50),
                        workload=dict(_DEFAULT_WORKLOAD),
                        monthly_budget=settings.employee_budget_default_monthly,
                        authority_level=authority,
                        rationale=(
                            f"Blueprint role {role.get('title', role_name)}"
                            + (
                                " (matches existing org role)"
                                if role_name in existing_roles
                                else ""
                            )
                        ),
                    )
                )

        total = sum(d.count for d in demand)
        if total > self.max_employees:
            raise ValueError(
                f"Workforce plan exceeds MAX_AUTONOMOUS_EMPLOYEES "
                f"({total} > {self.max_employees}); reduce roles or raise the cap"
            )
        return demand

    def persist(self, plan: StartupPlan, demand: list[WorkforceDemand]) -> WorkforcePlan:
        workforce = WorkforcePlan(
            startup_plan_id=plan.id,
            demand=json.dumps([d.to_dict() for d in demand], default=str),
            approval_policy=json.dumps(
                {
                    "requires_approval_for": ["company_admin"],
                    "max_employees": self.max_employees,
                }
            ),
        )
        self._db.add(workforce)
        self._db.commit()
        return workforce


def _existing_role_names(db: Session, company_id) -> set[str]:
    return {r.name for r in RoleManager(db).list_(company_id=company_id)}
