"""Employee provisioning — the only way AI employees join a startup company.

:class:`EmployeeProvisioner` turns planned :class:`WorkforceDemand` into real
employees using the Phase 7 :class:`EmployeeManager` (which auto-creates a
backing agent + budget) and the Phase 8 :class:`CompanyManager` memberships —
no second employee or membership system. Provisioning is *controlled*: it
respects the autonomy policy (action ``provision_employee``), the company's
``MAX_AUTONOMOUS_EMPLOYEES`` cap, the provisioning rate limit, and the
authority/role/scope derived from the organizational blueprint. Direct calls
to ``EmployeeManager.create`` outside this class circumvent none of these
checks because the engine only ever provisions through this path.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.manager import CompanyManager
from app.company.roles import AuthorityLevel, RoleManager
from app.db.models.employee import AIEmployee
from app.db.models.startup import MissionGraphRelation, WorkforcePlan
from app.employee.manager import EmployeeManager
from app.startup.autonomy import AutonomyService
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.graph import MissionGraphBuilder
from app.startup.types import WorkforceDemand


class EmployeeProvisioner:
    """Provision employees from planned workforce demand, under governance."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    # ── Public API ─────────────────────────────────────────────────────

    def provision(
        self,
        *,
        company_id: UUID,
        demand: list[WorkforceDemand],
        approved_gate_id: UUID | None = None,
        actor: str = "system",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Provision employees for a demand list.

        ``approved_gate_id`` supplies an approved WORKFORCE_APPROVAL /
        COMPANY_BOOTSTRAP_APPROVAL gate when the autonomy policy classifies
        provisioning as requiring approval.
        """
        # 1. Governance: the autonomy policy decides before anything is created.
        autonomy = AutonomyService(self._db)
        autonomy.enforce(
            "provision_employee",
            company_id,
            actor=actor,
            approved_gate_id=approved_gate_id,
        )
        policy = autonomy.get_policy(company_id)

        # 2. Limits: absolute employee cap (company policy + settings).
        existing = self._count_employees(company_id)
        cap = policy.max_employees
        capped = cap is not None and cap < self._settings_max()
        effective_cap = cap if capped else self._settings_max()
        if existing + sum(d.count for d in demand) > effective_cap:
            raise ValueError(
                f"Provisioning would exceed MAX_AUTONOMOUS_EMPLOYEES "
                f"({existing + sum(d.count for d in demand)} > {effective_cap})"
            )

        # 3. Rate limit: number of employees created per provisioning pass.
        rate = policy.max_provisioning_rate or limit or 0
        total_demand = sum(d.count for d in demand)
        if rate and total_demand > rate:
            raise ValueError(f"Provisioning rate exceeded (requested {total_demand} > {rate})")

        # 4. Provision.
        provisioned: list[dict[str, Any]] = []
        for entry in demand:
            for _ in range(max(1, entry.count)):
                provisioned.append(
                    self._provision_one(
                        company_id, entry, actor=actor, gate_approved=approved_gate_id is not None
                    )
                )
        return provisioned

    def provision_from_workforce_plan(
        self,
        *,
        company_id: UUID,
        workforce_plan: WorkforcePlan,
        approved_gate_id: UUID | None = None,
        actor: str = "system",
    ) -> list[dict[str, Any]]:
        demand = _loads_list(workforce_plan, "demand")
        return self.provision(
            company_id=company_id,
            demand=demand,
            approved_gate_id=approved_gate_id,
            actor=actor,
        )

    # ── Internals ──────────────────────────────────────────────────────

    def _provision_one(
        self,
        company_id: UUID,
        entry: WorkforceDemand,
        *,
        actor: str,
        gate_approved: bool,
    ) -> dict[str, Any]:
        """Create + activate + membership for a single employee."""
        role = self._resolve_role(company_id, entry)
        dept = self._resolve_department(company_id, entry.department)
        authority = role.authority_level
        permissions = _permissions_for(authority)

        employees = EmployeeManager(self._db)
        # Unique identity: blueprint role name + index when repeated.
        base_name = _slug(role.name or entry.role)
        name = _unique_employee_name(self._db, base_name)
        employee = employees.create(
            name=name,
            display_name=role.title or role.name,
            description=(f"{role.description}" or f"{role.title} for the startup company"),
            role=role.name,
            department=entry.department or dept.name if dept else None,
            skills=[{"name": s, "level": 3} for s in (entry.skills or [])],
            responsibilities=_loads_list2(role.responsibilities),
            permissions=permissions,
            policies={},
            workload_config=entry.workload or dict(),
        )
        employees.activate(employee.id)

        membership = CompanyManager(self._db).add_membership(
            company_id=company_id,
            employee_id=employee.id,
            department_id=dept.id if dept else None,
            role_id=role.id,
            responsibility="ic",
        )
        self._events.log(
            action=StartupEvents.EMPLOYEE_PROVISIONED,
            company_id=company_id,
            actor=actor,
            target_type="employee",
            target_id=employee.id,
            details={
                "name": employee.name,
                "role": role.name,
                "department": entry.department,
                "authority": authority.value,
                "gate_approved": gate_approved,
            },
            outcome="success",
        )
        if role.id is not None:
            MissionGraphBuilder(self._db).link(
                company_id=company_id,
                source_type="employee",
                source_id=employee.id,
                target_type="role",
                target_id=role.id,
                relation=MissionGraphRelation.ASSIGNED_TO,
                metadata={"authority": authority.value},
            )
        return {
            "employee_id": str(employee.id),
            "agent_id": str(employee.agent_id) if employee.agent_id else None,
            "name": employee.name,
            "role": role.name,
            "authority": authority.value,
            "department": entry.department,
            "membership_id": membership.get("id"),
            "skills": entry.skills,
        }

    def _resolve_role(self, company_id: UUID, entry: WorkforceDemand):
        role = RoleManager(self._db).find_by_name(company_id, entry.role)
        if role is None:
            role = RoleManager(self._db).create(
                name=entry.role,
                title=_title_for(entry.role, authority=entry.authority_level),
                company_id=company_id,
                description=f"Blueprint role '{entry.role}'",
                responsibilities=[f"Execute {entry.role} work"],
                required_skills=entry.skills,
                authority_level=AuthorityLevel(entry.authority_level or "individual_contributor"),
                compatible_departments=[entry.department] if entry.department else None,
            )
        return role

    def _resolve_department(self, company_id: UUID, name: str | None):
        if not name:
            return None
        from app.company.manager import CompanyManager

        for dept in CompanyManager(self._db).get_departments(company_id):
            if dept.name == name:
                return dept
        from app.company.departments import DepartmentManager

        return DepartmentManager(self._db).create(
            company_id=company_id,
            name=name,
            description=f"Department for '{name}'",
        )

    # ── Helpers ────────────────────────────────────────────────────────

    def _count_employees(self, company_id: UUID) -> int:
        return len(CompanyManager(self._db).get_memberships(company_id))

    def _settings_max(self) -> int:
        from app.core.config import settings

        return settings.startup_max_employees


# ── Module helpers ───────────────────────────────────────────────────────────


def _permissions_for(authority: AuthorityLevel) -> list[str]:
    perms = ["execute_tasks"]
    if authority in (
        AuthorityLevel.MANAGER,
        AuthorityLevel.EXECUTIVE,
        AuthorityLevel.COMPANY_ADMIN,
    ):
        perms.append("manage_team")
    if authority in (AuthorityLevel.EXECUTIVE, AuthorityLevel.COMPANY_ADMIN):
        perms.append("approve_high_risk")
    if authority == AuthorityLevel.COMPANY_ADMIN:
        perms += ["manage_company", "override_autonomy_limits"]
    return perms


def _title_for(role: str, *, authority: str | None) -> str:
    if authority == "company_admin":
        return f"{role.title()} Director"
    if authority in ("executive", "manager"):
        return f"{role.title()} Lead"
    return f"{role.title()} Specialist"


def _slug(role: str) -> str:
    return role.strip().lower().replace(" ", "_").replace("-", "_")


def _unique_employee_name(db: Session, base: str) -> str:
    existing = set(db.execute(select(AIEmployee.name)).scalars().all())
    if base not in existing:
        return base
    i = 2
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"


def _loads_list(wf: WorkforcePlan, key: str) -> list[WorkforceDemand]:
    raw = getattr(wf, key)
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return [_demand_from_dict(d) for d in value if isinstance(d, dict)]


def _demand_from_dict(d: dict[str, Any]) -> WorkforceDemand:
    return WorkforceDemand(
        role=str(d.get("role", "employee")),
        department=d.get("department"),
        count=int(d.get("count", 1)),
        skills=[str(s) for s in (d.get("skills") or [])],
        priority=int(d.get("priority", 0)),
        workload=dict(d.get("workload") or {}),
        monthly_budget=float(d.get("monthly_budget", 0.0)),
        authority_level=str(d.get("authority_level", "individual_contributor")),
        rationale=d.get("rationale"),
    )


def _loads_list2(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return [str(v) for v in value] if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
