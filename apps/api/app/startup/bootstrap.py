"""Company bootstrap — turn an approved startup plan into a working company.

``CompanyBootstrapper`` operates on the mission's **existing** company (Phase 8
:class:`Company`) — it configures and activates it, then materializes the
startup plan: departments, organizational roles, workforce provisioning, KPIs,
budgets, initial products, initial projects, and company goals. Everything is
built on Phase 7–8 services; no parallel company/employee/department system is
created. Provisioning runs through :class:`EmployeeProvisioner`, which applies
the autonomy policy (``provision_employee``) and the employee caps, and the
whole bootstrap is governed by a ``COMPANY_BOOTSTRAP_APPROVAL`` gate whenever
the policy requires approval.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.company.budget import BudgetManager
from app.company.kpis import KPIService
from app.company.manager import CompanyManager
from app.company.roles import AuthorityLevel, RoleManager
from app.db.models.company import GoalScopeType
from app.db.models.startup import (
    ApprovalGateType,
    MissionGraphRelation,
    MissionStatus,
    StartupPlan,
    StartupPlanStatus,
)
from app.startup.autonomy import AutonomyService
from app.startup.blueprint import BlueprintBuilder
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.gates import ApprovalGateManager
from app.startup.graph import MissionGraphBuilder
from app.startup.products import ProductManager
from app.startup.projects import ProjectManager
from app.startup.provision import EmployeeProvisioner
from app.startup.workforce import WorkforcePlanner

_KPI_SOURCE_METRICS = {
    "task_success_rate",
    "verification_rate",
    "recovery_rate",
    "failure_rate",
    "task_volume",
    "completed_tasks",
    "average_latency_ms",
    "budget_utilization",
    "total_cost",
    "employee_utilization",
    "goal_progress",
    "verification_volume",
    "active_employees",
}


class CompanyBootstrapper:
    """Materialize an approved startup plan on the mission's company."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    def bootstrap(
        self,
        plan: StartupPlan,
        *,
        approved_gate_id: UUID | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        if plan.status.value != "approved":
            raise ValueError(
                f"Startup plan is {plan.status.value}; only approved plans can be bootstrapped"
            )
        company_id = plan.mission.company_id

        # Governance: provisioning is the gating action of bootstrap.
        provisioner = EmployeeProvisioner(self._db)
        autonomy = AutonomyService(self._db)
        decision, reason = autonomy.decision("provision_employee", company_id)
        del decision
        working_gate_id = approved_gate_id
        if reason.startswith("'provision_employee' requires"):
            gate_manager = ApprovalGateManager(self._db)
            if approved_gate_id is None:
                gate = gate_manager.require_approved(
                    company_id,
                    ApprovalGateType.COMPANY_BOOTSTRAP_APPROVAL,
                    "provision_employee",
                    reason,
                )
                working_gate_id = gate.id
        autonomy.enforce("provision_employee", company_id, approved_gate_id=working_gate_id)

        # 1. Configure + activate the company itself.
        company = self._configure_company(plan, company_id)

        # 2. Blueprint + workforce plan (recorded, deterministic).
        blueprint_builder = BlueprintBuilder(self._db)
        blueprint = blueprint_builder.persist(plan, name=f"{plan.mission.title} blueprint")
        demand = WorkforcePlanner(self._db).plan(plan, blueprint=blueprint_builder.build(plan))
        workforce = WorkforcePlanner(self._db).persist(plan, demand)

        # 3. Departments + roles, then provision employees.
        dept_ids = self._create_departments_and_roles(company_id, plan)
        self._events.log(
            action=StartupEvents.BLUEPRINT_GENERATED,
            company_id=company_id,
            target_type="organizational_blueprint",
            target_id=blueprint.id,
            details={"name": blueprint.name, "departments": len(dept_ids)},
            outcome="success",
        )
        self._events.log(
            action=StartupEvents.WORKFORCE_PLANNED,
            company_id=company_id,
            target_type="workforce_plan",
            target_id=workforce.id,
            details={"demand_roles": len(demand)},
            outcome="success",
        )
        provisioned = provisioner.provision(
            company_id=company_id,
            demand=demand,
            approved_gate_id=working_gate_id,
            actor=actor,
        )

        # 4. KPIs + budgets.
        kpi_count = self._create_kpis(company_id, plan)
        budget_count = self._create_budgets(company_id, plan, dept_ids)

        # 5. Initial products + projects.
        products = self._create_products(company_id, plan)
        projects = self._create_projects(company_id, plan, products)

        # 6. Company goals from plan business/product objectives.
        goal_count = self._create_company_goals(company_id, plan)

        # 7. Statuses.
        plan.status = StartupPlanStatus.ACTIVE
        plan.mission.status = MissionStatus.ACTIVE
        self._db.commit()

        self._events.log(
            action=StartupEvents.COMPANY_BOOTSTRAPPED,
            company_id=company_id,
            target_type="company",
            target_id=company_id,
            details={
                "employees": len(provisioned),
                "departments": len(dept_ids),
                "kpis": kpi_count,
                "budgets": budget_count,
                "products": len(products),
                "projects": len(projects),
                "goals": goal_count,
            },
            outcome="success",
        )
        return {
            "company_id": str(company_id),
            "company_name": company.name,
            "departments": dept_ids,
            "employees": provisioned,
            "kpis": kpi_count,
            "budgets": budget_count,
            "products": products,
            "projects": projects,
            "goals": goal_count,
            "workforce_plan_id": str(workforce.id),
            "blueprint_id": str(blueprint.id),
        }

    # ── Helpers ────────────────────────────────────────────────────────

    def _configure_company(self, plan: StartupPlan, company_id: UUID):
        company_manager = CompanyManager(self._db)
        company = company_manager.get(company_id)
        if company is None:
            raise ValueError("Mission company does not exist")
        priorities = _loads(plan.execution_priorities)
        company_manager.update(
            company_id,
            mission=plan.mission.mission_statement,
            vision=(plan.mission.desired_outcome or company.vision),
            industry=company.industry,
            strategic_priorities=priorities,
            description=(company.description or plan.mission.description),
        )
        if company.status.value == "draft":
            company_manager.activate(company_id)
        return company_manager.get(company_id)

    def _create_departments_and_roles(self, company_id: UUID, plan: StartupPlan) -> dict[str, UUID]:
        """Create blueprint departments + their roles; return dept name → id."""
        data = BlueprintBuilder(self._db).build(plan)
        manager = CompanyManager(self._db)
        roles = RoleManager(self._db)
        dept_ids: dict[str, UUID] = {}
        for dept in data.departments:
            department = manager.create_department(
                company_id=company_id,
                name=dept.name,
                mission=dept.mission,
                description=f"Blueprint department '{dept.name}'",
            )
            dept_ids[dept.name] = department.id
            for role in dept.roles:
                role_name = str(role.get("name", dept.name.lower() + "_member")) if role else None
                if not role_name:
                    continue
                if roles.find_by_name(company_id, role_name) is not None:
                    continue
                roles.create(
                    name=role_name,
                    title=str(role.get("title", role_name)),
                    company_id=company_id,
                    description=str(role.get("description") or ""),
                    responsibilities=[str(r) for r in (role.get("responsibilities") or [])],
                    required_skills=[str(s) for s in (role.get("required_skills") or [])],
                    authority_level=AuthorityLevel(
                        str(role.get("authority_level", "individual_contributor"))
                    ),
                    compatible_departments=[dept.name],
                )
        return dept_ids

    def _create_kpis(self, company_id: UUID, plan: StartupPlan) -> int:
        data = BlueprintBuilder(self._db).build(plan)
        targets = _loads(plan.kpi_targets)
        kpi_service = KPIService(self._db)
        count = 0
        wanted: list[dict[str, Any]] = list(data.kpis)
        for name, target in targets.items():
            if not any(k.get("name") == name for k in wanted):
                wanted.append({"name": name, "target": target})
        existing = {k.name for k in kpi_service.list_(company_id)}
        for kpi_cfg in wanted:
            name = str(kpi_cfg.get("name", ""))
            if name not in _KPI_SOURCE_METRICS:
                continue  # only authoritative source metrics become real KPIs
            if name in existing:
                continue  # idempotent across replans/reboots
            kpi_service.create(
                company_id=company_id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company_id,
                name=name,
                source_metric=name,
                target=float(kpi_cfg.get("target")) if kpi_cfg.get("target") is not None else None,
                frequency="cycle",
            )
            count += 1
        return count

    def _create_budgets(
        self, company_id: UUID, plan: StartupPlan, dept_ids: dict[str, UUID]
    ) -> int:
        budget_manager = BudgetManager(self._db)
        allocation = _loads(plan.budget_allocation)
        count = 0
        company_limit = allocation.get("company") if isinstance(allocation, dict) else None
        if company_limit is not None:
            budget = budget_manager.ensure_budget(
                company_id,
                GoalScopeType.COMPANY,
                company_id,
                monthly_limit=float(company_limit),
            )
            budget = budget_manager.set_allocation(
                budget.id, monthly_limit=float(company_limit), actor="bootstrap"
            )
            del budget
            count += 1
        dept_alloc = (
            (allocation or {}).get("departments", {}) if isinstance(allocation, dict) else {}
        )
        for dept_name, amount in dept_alloc.items():
            dept_id = dept_ids.get(str(dept_name))
            if dept_id is None:
                continue
            budget = budget_manager.ensure_budget(
                company_id,
                GoalScopeType.DEPARTMENT,
                dept_id,
                monthly_limit=float(amount),
            )
            budget_manager.set_allocation(budget.id, monthly_limit=float(amount), actor="bootstrap")
            count += 1
        return count

    def _create_products(self, company_id: UUID, plan: StartupPlan) -> list[dict[str, Any]]:
        manager = ProductManager(self._db)
        created: list[dict[str, Any]] = []
        for cfg in _loads_list(plan.initial_products):
            if not isinstance(cfg, dict) or not cfg.get("name"):
                continue
            product = manager.create(
                company_id=company_id,
                name=str(cfg["name"]),
                description=cfg.get("description"),
                product_type=cfg.get("product_type"),
                target_users=[str(u) for u in (cfg.get("target_users") or [])],
                value_proposition=cfg.get("value_proposition"),
                strategic_priority=int(cfg.get("strategic_priority", 1)),
                budget=cfg.get("budget"),
                success_metrics=[str(s) for s in (cfg.get("success_metrics") or [])],
                launch_criteria=[str(c) for c in (cfg.get("launch_criteria") or [])],
            )
            MissionGraphBuilder(self._db).link(
                company_id=company_id,
                source_type="product",
                source_id=product.id,
                target_type="mission",
                target_id=plan.mission_id,
                relation=MissionGraphRelation.DERIVED_FROM,
            )
            created.append(manager.to_dict(product))
        return created

    def _create_projects(
        self,
        company_id: UUID,
        plan: StartupPlan,
        products: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        manager = ProjectManager(self._db)
        product_by_name = {
            (p.get("name") or "").lower(): UUID(p["id"]) for p in products if p.get("id")
        }
        created: list[dict[str, Any]] = []
        for cfg in _loads_list(plan.initial_projects):
            if not isinstance(cfg, dict) or not cfg.get("name"):
                continue
            product_id = None
            if cfg.get("product"):
                product_id = product_by_name.get(str(cfg["product"]).lower())
            project = manager.create(
                company_id=company_id,
                name=str(cfg["name"]),
                description=cfg.get("description"),
                objective=cfg.get("objective"),
                product_id=product_id,
                priority=int(cfg.get("priority", 0)),
                milestones=cfg.get("milestones"),
                success_criteria=[str(s) for s in (cfg.get("success_criteria") or [])],
            )
            created.append(manager.to_dict(project))
        return created

    def _create_company_goals(self, company_id: UUID, plan: StartupPlan) -> int:
        manager = CompanyManager(self._db)
        objectives = []
        for field in ("business_objectives", "product_objectives"):
            objectives.extend(_loads_list(getattr(plan, field)))
        count = 0
        for i, obj in enumerate(objectives[:8], start=1):
            title = (
                obj
                if isinstance(obj, str)
                else (obj.get("title") if isinstance(obj, dict) else None)
            )
            if not title:
                continue
            manager.create_goal(
                company_id=company_id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company_id,
                title=str(title),
                description=(obj.get("description") if isinstance(obj, dict) else None),
                priority=i,
            )
            count += 1
        return count


# ── Module helpers ───────────────────────────────────────────────────────────


def _loads(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _loads_list(raw: str | None) -> list[Any]:
    value = _loads(raw)
    return list(value) if isinstance(value, list) else []
