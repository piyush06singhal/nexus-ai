"""AI Company Layer — company manager (facade).

Composes the organizational services into the company-level operations used by
the API and demos: CRUD + lifecycle for the company itself, plus the read
endpoints for the executive dashboard. This is the single entry point the
``/companies`` router calls. All aggregates come from the real services backed
by authoritative tables.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.alerts import AlertManager, CompanyHealth
from app.company.analytics import AnalyticsService, ForecastService
from app.company.budget import BudgetManager
from app.company.departments import DepartmentManager
from app.company.events import OrgEventLogger
from app.company.goals import GoalManager
from app.company.kpis import KPIService
from app.company.lifecycle import (
    validate_company_transition,
)
from app.company.membership import MembershipManager
from app.company.orgchart import OrgChartBuilder
from app.company.performance import PerformanceAggregator
from app.company.policies import PolicyManager, PolicyResolver
from app.company.reports import ReportGenerator
from app.company.risks import RiskManager
from app.company.roles import RoleManager
from app.db.models.company import (
    Company,
    CompanyStatus,
    Department,
    GoalScopeType,
)
from app.schemas.company import CompanyRead, DepartmentRead, OrgChartNodeRead


class CompanyManager:
    """CRUD + lifecycle + dashboard composition for a company."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)
        self.departments = DepartmentManager(db)
        self.memberships = MembershipManager(db)
        self.roles = RoleManager(db)
        self.goals = GoalManager(db)
        self.kpis = KPIService(db)
        self.budget_manager = BudgetManager(db)
        self.policies = PolicyManager(db)
        self.risks = RiskManager(db)
        self.alerts = AlertManager(db)
        self.health_compute = CompanyHealth(db)
        self._analytics_svc = AnalyticsService(db)
        self.forecasts = ForecastService(db)
        self.performance_aggregator = PerformanceAggregator(db)
        self.reports_service = ReportGenerator(db)

    # ── CRUD ───────────────────────────────────────────────────────────

    def create(
        self,
        *,
        name: str,
        description: str | None = None,
        mission: str | None = None,
        vision: str | None = None,
        industry: str | None = None,
        timezone: str | None = None,
        currency: str | None = "USD",
    ) -> Company:
        company = Company(
            name=name,
            slug=_slugify(name),
            description=description,
            mission=mission,
            vision=vision,
            industry=industry,
            timezone=timezone or "UTC",
            currency=currency or "USD",
            status=CompanyStatus.DRAFT,
        )
        self._db.add(company)
        self._db.flush()
        self.events.log(
            actor="system",
            action="company_created",
            company_id=company.id,
            target_type="company",
            target_id=company.id,
            details={"name": name},
            outcome="success",
        )
        self._db.commit()
        return company

    def get(self, company_id: UUID) -> Company | None:
        return self._db.get(Company, company_id)

    def list_(self) -> list[Company]:
        stmt = select(Company).order_by(Company.created_at.desc())
        return list(self._db.execute(stmt).scalars().all())

    def update(self, company_id: UUID, **fields: Any) -> Company:
        company = self._require(company_id)
        if company.status == CompanyStatus.ARCHIVED:
            raise ValueError("Archived companies are read-only")
        for key, value in fields.items():
            if not hasattr(company, key) or value is None:
                continue
            if key in ("values", "strategic_priorities"):
                setattr(company, key, json.dumps(value))
            else:
                setattr(company, key, value)
        self._db.commit()
        return company

    def _require(self, company_id: UUID) -> Company:
        company = self._db.get(Company, company_id)
        if company is None:
            raise ValueError("Company not found")
        return company

    # ── Lifecycle ──────────────────────────────────────────────────────

    def _transition(self, company_id: UUID, target: CompanyStatus) -> Company:
        company = self._require(company_id)
        validate_company_transition(company.status, target)
        company.status = target
        self._db.flush()
        self.events.log(
            actor="system",
            action=f"company_{target.value}",
            company_id=company.id,
            target_type="company",
            target_id=company.id,
            details={"from": company.status.value, "to": target.value},
            outcome="success",
        )
        self._db.commit()
        return company

    def activate(self, company_id: UUID) -> Company:
        return self._transition(company_id, CompanyStatus.ACTIVE)

    def pause(self, company_id: UUID) -> Company:
        return self._transition(company_id, CompanyStatus.PAUSED)

    def archive(self, company_id: UUID) -> Company:
        return self._transition(company_id, CompanyStatus.ARCHIVED)

    # ── Serialization ──────────────────────────────────────────────────

    def to_read(self, company: Company) -> CompanyRead:
        return CompanyRead(
            id=company.id,
            name=company.name,
            slug=company.slug,
            description=company.description,
            mission=company.mission,
            vision=company.vision,
            industry=company.industry,
            timezone=company.timezone,
            currency=company.currency,
            values=_loads_list(company.values),
            strategic_priorities=_loads_list(company.strategic_priorities),
            status=company.status,
            owner_id=company.owner_id,
            created_at=company.created_at,
            updated_at=company.updated_at,
        )

    def to_dept_read(self, dept: Department) -> DepartmentRead:
        return DepartmentRead(
            id=dept.id,
            company_id=dept.company_id,
            name=dept.name,
            description=dept.description,
            mission=dept.mission,
            manager_id=dept.manager_id,
            parent_department_id=dept.parent_department_id,
            status=dept.status,
            created_at=dept.created_at,
            updated_at=dept.updated_at,
        )

    # ── Departments ────────────────────────────────────────────────────

    def create_department(
        self,
        *,
        company_id: UUID,
        name: str,
        description: str | None = None,
        mission: str | None = None,
        manager_id: UUID | None = None,
        parent_department_id: UUID | None = None,
    ) -> Department:
        self._require(company_id)
        return self.departments.create(
            company_id=company_id,
            name=name,
            description=description,
            mission=mission,
            manager_id=manager_id,
            parent_department_id=parent_department_id,
        )

    def get_departments(self, company_id: UUID) -> list[Department]:
        return self.departments.list_(company_id)

    # ── Employees / memberships ────────────────────────────────────────

    def company_employees(self, company_id: UUID) -> list[dict[str, Any]]:
        """All employees in the company, with role/department enrichment."""
        emps = self.memberships.list_employees(company_id)
        return [self._enrich_employee(e, company_id) for e in emps]

    def _enrich_employee(self, employee, company_id: UUID) -> dict[str, Any]:
        membership = self.memberships.get(company_id, employee.id)
        role = self.memberships.role_of(membership) if membership else None
        return {
            "id": str(employee.id),
            "name": employee.name,
            "display_name": employee.display_name,
            "role": employee.role,
            "department": employee.department,
            "status": getattr(employee.status, "value", employee.status),
            "agent_id": str(employee.agent_id) if employee.agent_id else None,
            "skills": _loads_list(employee.skills),
            "responsible_scope": (
                {
                    "department_id": (
                        str(membership.department_id) if membership.department_id else None
                    ),
                    "role_id": str(membership.role_id) if membership.role_id else None,
                    "authority_level": (role.authority_level.value if role else None),
                    "manager_id": str(membership.manager_id) if membership.manager_id else None,
                }
                if membership
                else None
            ),
        }

    def get_memberships(self, company_id: UUID) -> list[dict[str, Any]]:
        memberships = self.memberships.list(company_id)
        return [self.memberships.to_dict(m) for m in memberships]

    def add_membership(
        self,
        *,
        company_id: UUID,
        employee_id: UUID,
        department_id: UUID | None = None,
        role_id: UUID | None = None,
        manager_id: UUID | None = None,
        responsibility: str = "ic",
    ) -> dict[str, Any]:
        self._require(company_id)
        membership = self.memberships.add(
            company_id=company_id,
            employee_id=employee_id,
            department_id=department_id,
            role_id=role_id,
            manager_id=manager_id,
            responsibility=responsibility,
        )
        return self.memberships.to_dict(membership)

    def update_membership(
        self,
        membership_id: UUID,
        *,
        department_id: UUID | None = None,
        role_id: UUID | None = None,
        manager_id: UUID | None = None,
        responsibility: str | None = None,
    ) -> dict[str, Any]:
        membership = self.memberships.update(
            membership_id,
            department_id=department_id,
            role_id=role_id,
            manager_id=manager_id,
            responsibility=responsibility,
        )
        return self.memberships.to_dict(membership)

    def remove_membership(self, membership_id: UUID) -> bool:
        return self.memberships.remove(membership_id)

    def organization_chart(self, company_id: UUID) -> OrgChartNodeRead:
        company = self._require(company_id)
        chart = OrgChartBuilder(self._db).build(company_id, company.name)
        return self._chart_node_to_read(chart.root)

    def _chart_node_to_read(self, node) -> OrgChartNodeRead:
        return OrgChartNodeRead(
            id=node.id,
            type=node.type,
            name=node.name,
            status=node.status,
            children=[self._chart_node_to_read(c) for c in node.children],
        )

    # ── Goals ──────────────────────────────────────────────────────────

    def create_goal(
        self,
        *,
        company_id: UUID,
        scope_type: GoalScopeType,
        scope_id: UUID,
        title: str,
        description: str | None = None,
        parent_goal_id: UUID | None = None,
        priority: str | None = None,
        target: float | None = None,
        metric: str | None = None,
        deadline=None,
        owner_id: UUID | None = None,
    ) -> dict[str, Any]:
        self._require(company_id)
        goal = self.goals.create(
            company_id=company_id,
            scope_type=scope_type,
            scope_id=scope_id,
            title=title,
            description=description,
            parent_goal_id=parent_goal_id,
            priority=int(priority) if priority else 0,
            target=str(target) if target is not None else None,
            metric=metric,
            deadline=deadline,
            owner_id=owner_id,
        )
        return self.goals.to_dict(goal)

    def get_goals(self, company_id: UUID, *, scope_type: str | None = None) -> list[dict[str, Any]]:
        goals = self.goals.list(company_id)
        if scope_type:
            goals = [g for g in goals if g.scope_type.value == scope_type]
        return [self.goals.to_dict(g) for g in goals]

    def goal_tree(self, company_id: UUID) -> list[dict[str, Any]]:
        return self.goals.tree(company_id)

    # ── KPIs ───────────────────────────────────────────────────────────

    def create_kpi(self, *, company_id: UUID, **fields: Any) -> dict[str, Any]:
        self._require(company_id)
        kpi = self.kpis.create(company_id=company_id, **fields)
        return self.kpis.snapshot(kpi)

    def get_kpis(self, company_id: UUID, *, scope_type: str | None = None) -> list[dict[str, Any]]:
        kpis = self.kpis.list_(company_id)
        if scope_type:
            kpis = [k for k in kpis if k.scope_type.value == scope_type]
        return [self.kpis.snapshot(k) for k in kpis]

    def recompute_kpis(self, company_id: UUID) -> dict[str, Any]:
        readings = self.kpis.recompute_all(company_id)
        return {"recomputed": len(readings)}

    # ── Budgets ────────────────────────────────────────────────────────

    def budgets(self, company_id: UUID) -> dict[str, Any]:
        company_budget = self.budget_manager.snapshot(company_id, GoalScopeType.COMPANY, company_id)
        dept_budgets = []
        for budget in self.budget_manager.department_budgets(company_id):
            snap = self.budget_manager.snapshot(
                company_id, GoalScopeType.DEPARTMENT, budget.scope_id
            )
            if snap is not None:
                dept_budgets.append(_budget_snap_dict(snap))
        return {
            "company": _budget_snap_dict(company_budget) if company_budget else None,
            "departments": dept_budgets,
        }

    # ── Performance / reports ──────────────────────────────────────────

    def performance(self, company_id: UUID) -> dict[str, Any]:
        return self.performance_service().aggregate(company_id)

    def reports(self, company_id: UUID, *, report_type: str | None = None) -> list[dict[str, Any]]:
        reports = self.reports_service.list_(company_id, report_type=report_type)
        return [self.reports_service.to_dict(r) for r in reports]

    # ── Risks ──────────────────────────────────────────────────────────

    def create_risk(self, *, company_id: UUID, **fields: Any) -> dict[str, Any]:
        self._require(company_id)
        risk = self.risks.create(company_id=company_id, **fields)
        return self.risks.to_dict(risk)

    def get_risks(self, company_id: UUID, *, severity: str | None = None) -> list[dict[str, Any]]:
        risks = self.risks.list_(company_id, severity=severity)
        return [self.risks.to_dict(r) for r in risks]

    # ── Alerts ─────────────────────────────────────────────────────────

    def get_alerts(self, company_id: UUID, *, severity: str | None = None) -> list[dict[str, Any]]:
        from app.db.models.company import AlertSeverity

        sev = AlertSeverity(severity) if severity else None
        alerts = self.alerts.list_(company_id, severity=sev)
        return [self.alerts.to_dict(a) for a in alerts]

    def check_alerts(self, company_id: UUID) -> dict[str, Any]:
        generated = self.alerts.generate_alerts(company_id)
        return {"generated": len(generated), "alerts": [self.alerts.to_dict(a) for a in generated]}

    # ── Analytics / health ─────────────────────────────────────────────

    def analytics(self, company_id: UUID) -> dict[str, Any]:
        return self.analytics_service().full_analytics(company_id)

    def health(self, company_id: UUID) -> dict[str, Any]:
        return self.health_compute.compute(company_id)

    # ── Timeline ───────────────────────────────────────────────────────

    def timeline(self, company_id: UUID, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.events.timeline(company_id, limit=limit)

    # ── Policies ───────────────────────────────────────────────────────

    def create_policy(self, *, company_id: UUID, **fields: Any) -> dict[str, Any]:
        self._require(company_id)
        policy = self.policies.create(company_id=company_id, **fields)
        return self.policies.to_dict(policy)

    def get_policies(self, company_id: UUID) -> list[dict[str, Any]]:
        return [self.policies.to_dict(p) for p in self.policies.list_(company_id)]

    def effective_policy(
        self,
        company_id: UUID,
        *,
        key: str,
        department_id: UUID | None = None,
    ) -> dict[str, Any]:
        resolver = PolicyResolver(self._db)
        detail = resolver.effective_detail(
            key,
            company_id=company_id,
            department_id=department_id,
        )
        applicable = detail.get("applicable_scopes", [])
        return {
            "key": detail["key"],
            "value": detail["value"],
            "source_scope": detail.get("source_scope"),
            "source_name": (
                f"{detail.get('source_scope')} policy" if detail.get("source_scope") else None
            ),
            "candidates_checked": len(applicable),
        }

    # ── Roles ──────────────────────────────────────────────────────────

    def get_roles(self, company_id: UUID) -> list[dict[str, Any]]:
        roles = self.roles.list_(company_id=company_id)
        return [self.roles.to_dict(r) for r in roles]

    # ── Internal service accessors ─────────────────────────────────────

    def performance_service(self) -> PerformanceAggregator:
        return self.performance_aggregator

    def analytics_service(self) -> AnalyticsService:
        return self._analytics_svc


def _slugify(name: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    return out if out else "company"


def _loads_list(raw) -> list | None:
    if not raw:
        return None
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else [val]
    except (json.JSONDecodeError, TypeError):
        return None


def _budget_snap_dict(snap) -> dict[str, Any]:
    return {
        "company_id": str(snap.company_id),
        "scope_type": snap.scope_type,
        "scope_id": str(snap.scope_id),
        "monthly_limit": snap.monthly_limit,
        "allocated": snap.allocated,
        "reserved": snap.reserved,
        "spent": snap.spent,
        "tokens_used": snap.tokens_used,
        "cost_used": snap.cost_used,
        "tool_calls_used": snap.tool_calls_used,
        "execution_count": snap.execution_count,
        "period_start": snap.period_start,
        "period_end": snap.period_end,
        "utilization_pct": round((snap.spent / snap.monthly_limit) * 100, 2)
        if snap.monthly_limit
        else 0.0,
    }
