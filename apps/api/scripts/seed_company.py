"""Seed the NEXUS AI Software Company demo (§82).

Creates the demo "NEXUS Labs" company through the real Company Layer services:

  companies → departments → roles → employees (with agents) → memberships →
  goals → budgets → KPIs → policies → risks → alerts → health snapshot.

Idempotent: if a company with the same name already exists, it is reused and
the seed fills in any missing pieces.

Run from ``apps/api``:
    .venv/bin/python -m scripts.seed_company [--name "NEXUS Labs"] [--reset]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

# Ensure ``app.db.session`` resolves when run as a script inside apps/api.
sys.path.insert(0, ".")

from app.db.models import (  # noqa: E402, F401 — register all ORM tables
    Agent,
    AIEmployee,
    AuthorityLevel,
    Company,
    CompanyStatus,
    Department,
    EmployeeStatus,
    GoalScopeType,
    PolicyScopeType,
    RiskStatus,
)
from app.db.session import Base, SessionLocal  # noqa: E402

# ── Demo definitions ──────────────────────────────────────────────────────────

DEMO_COMPANY = {
    "name": "NEXUS Labs",
    "description": "A demo AI-native software company running on the NEXUS framework.",
    "mission": "Build autonomous AI teams that ship high-quality software efficiently.",
    "vision": "Every knowledge organization runs on verifiable AI agents.",
    "industry": "ai",
    "values": ["customer-obsessed", "verifiable-by-default", "ownership", "transparency"],
    "strategic_priorities": [
        "Ship a competitive analysis report",
        "Increase verification coverage",
        "Reduce infrastructure cost",
    ],
}

DEPARTMENTS = [
    {"name": "Executive", "description": "Company leadership and strategy."},
    {"name": "Engineering", "description": "Builds and ships the product."},
    {"name": "Research", "description": "Market and technical research."},
    {"name": "Marketing", "description": "Go-to-market and brand."},
    {"name": "Operations", "description": "Run the business efficiently."},
]

EMPLOYEES = [
    {
        "name": "ceo",
        "display_name": "Ada Strategy",
        "role": "executive",
        "department": "Executive",
        "skills": ["strategy", "leadership", "communication"],
        "authority": AuthorityLevel.EXECUTIVE,
        "role_name": "ceo",
        "role_title": "Chief Executive Officer",
    },
    {
        "name": "cto",
        "display_name": "Alan Architect",
        "role": "cto",
        "department": "Executive",
        "skills": ["architecture", "python", "ai", "leadership"],
        "authority": AuthorityLevel.EXECUTIVE,
        "role_name": "cto",
        "role_title": "Chief Technology Officer",
        "manager": "ceo",
    },
    {
        "name": "eng-lead",
        "display_name": "Grace Manager",
        "role": "engineering-manager",
        "department": "Engineering",
        "skills": ["management", "python", "code-review"],
        "authority": AuthorityLevel.MANAGER,
        "role_name": "engineering_manager",
        "role_title": "Engineering Manager",
        "manager": "cto",
    },
    {
        "name": "backend-engineer",
        "display_name": "Barbara Builder",
        "role": "backend-engineer",
        "department": "Engineering",
        "skills": ["python", "sql", "api", "testing"],
        "authority": AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        "role_name": "backend_engineer",
        "role_title": "Backend Engineer",
        "manager": "eng-lead",
    },
    {
        "name": "ai-engineer",
        "display_name": "Marvin ML",
        "role": "ai-engineer",
        "department": "Engineering",
        "skills": ["python", "ml", "data-analysis", "evaluation"],
        "authority": AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        "role_name": "ai_engineer",
        "role_title": "AI Engineer",
        "manager": "eng-lead",
    },
    {
        "name": "research-lead",
        "display_name": "Carrie Radar",
        "role": "research-lead",
        "department": "Research",
        "skills": ["research", "analysis", "reporting"],
        "authority": AuthorityLevel.MANAGER,
        "role_name": "research_manager",
        "role_title": "Research Manager",
        "manager": "cto",
    },
    {
        "name": "research-analyst",
        "display_name": "Ronald Analyst",
        "role": "research-analyst",
        "department": "Research",
        "skills": ["research", "competitive-analysis", "writing"],
        "authority": AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        "role_name": "research_analyst",
        "role_title": "Research Analyst",
        "manager": "research-lead",
    },
    {
        "name": "marketing-specialist",
        "display_name": "Maya Growth",
        "role": "marketing-specialist",
        "department": "Marketing",
        "skills": ["copywriting", "social", "brand"],
        "authority": AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        "role_name": "marketing_specialist",
        "role_title": "Marketing Specialist",
        "manager": "ceo",
    },
    {
        "name": "ops-analyst",
        "display_name": "Oscar Ops",
        "role": "operations-analyst",
        "department": "Operations",
        "skills": ["budget", "reporting", "coordination"],
        "authority": AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        "role_name": "operations_analyst",
        "role_title": "Operations Analyst",
        "manager": "ceo",
    },
]

COMPANY_GOALS = [
    {
        "title": "Ship a competitive analysis report",
        "metric": "report_ready",
        "target": "1 report published",
        "priority": 30,
        "progress": 0.0,
    },
    {
        "title": "Increase verification coverage to 90%",
        "metric": "verification_rate",
        "target": "90%",
        "priority": 20,
        "progress": 0.65,
    },
    {
        "title": "Reduce monthly infra cost by 20%",
        "metric": "cost_reduction",
        "target": "-20%",
        "priority": 10,
        "progress": 0.3,
    },
]

DEPARTMENT_GOALS = {
    "Research": [
        {
            "title": "Draft competitive landscape analysis",
            "metric": "sections_drafted",
            "target": "5 sections",
            "priority": 25,
            "progress": 0.2,
        }
    ],
    "Engineering": [
        {
            "title": "Ship verification harness",
            "metric": "harness_shipped",
            "target": "1 harness",
            "priority": 25,
            "progress": 0.7,
        }
    ],
}

KPIS = [
    {
        "name": "Task Success Rate",
        "source_metric": "task_success_rate",
        "target": 90.0,
        "unit": "%",
    },
    {
        "name": "Verification Rate",
        "source_metric": "verification_rate",
        "target": 90.0,
        "unit": "%",
    },
    {"name": "Recovery Rate", "source_metric": "recovery_rate", "target": 85.0, "unit": "%"},
    {"name": "Task Volume", "source_metric": "task_volume", "target": 200.0, "unit": "tasks"},
    {
        "name": "Budget Utilization",
        "source_metric": "budget_utilization",
        "target": 80.0,
        "unit": "%",
    },
]

POLICIES = [
    {
        "scope_type": PolicyScopeType.COMPANY,
        "name": "Model Token Ceiling",
        "key": "max_tokens",
        "value": 8192,
    },
    {
        "scope_type": PolicyScopeType.COMPANY,
        "name": "Require Task Approval",
        "key": "require_approval",
        "value": False,
    },
    {
        "scope_type": PolicyScopeType.COMPANY,
        "name": "System Max Concurrency",
        "key": "max_concurrency",
        "value": 4,
    },
    {
        "scope_type": PolicyScopeType.SYSTEM,
        "name": "Global Rate Limit",
        "key": "rate_limit",
        "value": 100,
    },
]

RISKS = [
    {
        "title": "Verification coverage below target",
        "description": "Engineering verification rate may lag the 90% target.",
        "severity": "high",
        "status": RiskStatus.MITIGATING,
        "mitigation": "Prioritize verification harness tasks in the sprint.",
    },
    {
        "title": "Infrastructure cost overrun",
        "description": "Monthly spend trending above budget.",
        "severity": "medium",
        "status": RiskStatus.MONITORED,
        "mitigation": "Periodic budget review in the weekly operating cycle.",
    },
    {
        "title": "Competitive pressure",
        "description": "Two competitors shipping similar autonomous-agent features.",
        "severity": "medium",
        "status": RiskStatus.OPEN,
        "mitigation": "Research dept to produce the competitive analysis.",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_json(value: Any) -> str | None:
    return json.dumps(value) if value is not None else None


def _get_or_create_company(db: Session, name: str) -> Company:
    existing = db.scalar(select(Company).where(Company.slug == name.lower().replace(" ", "-")))
    if existing is not None:
        return existing
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name=name, description=DEMO_COMPANY["description"])


def _get_unused_agent_name(db: Session, base: str) -> str:
    existing = set(db.execute(select(Agent.name)).scalars())
    name = f"{base}-agent"
    i = 2
    while name in existing:
        name = f"{base}-agent-{i}"
        i += 1
    return name


def _seed_company(db: Session, name: str, *, reset: bool = False) -> dict[str, Any]:
    if reset:
        existing = db.scalar(select(Company).where(Company.slug == name.lower().replace(" ", "-")))
        if existing is not None:
            db.delete(existing)
            db.commit()

    from app.company.alerts import AlertManager
    from app.company.budget import BudgetManager
    from app.company.goals import GoalManager
    from app.company.kpis import KPIService
    from app.company.manager import CompanyManager
    from app.company.membership import MembershipManager
    from app.company.policies import PolicyManager
    from app.company.risks import RiskManager
    from app.company.roles import RoleManager
    from app.employee.manager import EmployeeManager

    company = _get_or_create_company(db, name)
    if company.status != CompanyStatus.ACTIVE:
        CompanyManager(db).activate(company.id)

    em = EmployeeManager(db)
    roles = RoleManager(db)
    memberships = MembershipManager(db)
    departments = DepartmentManagerProxy(db, company.id)
    goal_mgr = GoalManager(db)
    budget_mgr = BudgetManager(db)
    kpi_svc = KPIService(db)
    policy_mgr = PolicyManager(db)
    risk_mgr = RiskManager(db)
    alert_mgr = AlertManager(db)

    # Track created entities to return a useful summary.
    summary: dict[str, Any] = {
        "company_id": str(company.id),
        "company_name": company.name,
        "departments": [],
        "employees": [],
        "goals": 0,
        "kpis": 0,
        "policies": 0,
        "risks": 0,
        "alerts": 0,
        "health": None,
    }

    # ── Departments ───────────────────────────────────────────────────
    for d in DEPARTMENTS:
        dept = departments.get_or_create(d["name"], d["description"])
        summary["departments"].append(dept.id)

    # ── Roles (one per authority level per department group) ──────────
    role_ids: dict[str, UUID] = {}
    for e in EMPLOYEES:
        role = roles.find_by_name(company.id, e["role_name"])
        if role is None:
            role = roles.create(
                name=e["role_name"],
                title=e["role_title"],
                company_id=company.id,
                authority_level=e["authority"],
                required_skills=e["skills"],
                responsibilities=[f"Own {e['department'].lower()} responsibilities"],
            )
        role_ids[e["name"]] = role.id

    # ── Employees (agents auto-created) + memberships ─────────────────
    emp_ids: dict[str, UUID] = {}
    for e in EMPLOYEES:
        existing_emp = db.scalar(
            select(AIEmployee).where(
                AIEmployee.name == e["name"],
            )
        )
        if existing_emp is not None:
            employee = existing_emp
        else:
            employee = em.create(
                name=e["name"],
                display_name=e["display_name"],
                role=e["role"],
                department=e["department"],
                skills=e["skills"],
            )
            em.activate(employee.id)
        emp_ids[e["name"]] = employee.id
        summary["employees"].append(employee.id)

    dept_by_name = {d.name: d.id for d in departments.all()}
    for e in EMPLOYEES:
        employee_id = emp_ids[e["name"]]
        # Idempotent: skip members already added by a prior seed run.
        if memberships.get(company.id, employee_id) is not None:
            continue
        manager_name = e.get("manager")
        memberships.add(
            company_id=company.id,
            employee_id=employee_id,
            department_id=dept_by_name[e["department"]],
            role_id=role_ids[e["name"]],
            responsibility="manager"
            if e["authority"]
            in (
                AuthorityLevel.MANAGER,
                AuthorityLevel.EXECUTIVE,
            )
            else "ic",
            manager_id=emp_ids[manager_name] if manager_name else None,
        )

    from app.db.models.company import KPI, OrgGoal, Policy, Risk

    # ── Goals (company + department) — idempotent by (scope, title) ───
    company_goal_ids: list[UUID] = []
    for g in COMPANY_GOALS:
        existing = db.scalar(
            select(OrgGoal).where(
                OrgGoal.company_id == company.id,
                OrgGoal.scope_type == GoalScopeType.COMPANY,
                OrgGoal.title == g["title"],
            )
        )
        if existing is None:
            existing = goal_mgr.create(
                company_id=company.id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company.id,
                title=g["title"],
                metric=g.get("metric"),
                target=g.get("target"),
                priority=g.get("priority", 0),
                progress=g.get("progress", 0.0),
            )
        company_goal_ids.append(existing.id)
    for dept_name, goals in DEPARTMENT_GOALS.items():
        dept_id = dept_by_name[dept_name]
        for g in goals:
            existing = db.scalar(
                select(OrgGoal).where(
                    OrgGoal.company_id == company.id,
                    OrgGoal.scope_type == GoalScopeType.DEPARTMENT,
                    OrgGoal.scope_id == dept_id,
                    OrgGoal.title == g["title"],
                )
            )
            if existing is None:
                goal_mgr.create(
                    company_id=company.id,
                    scope_type=GoalScopeType.DEPARTMENT,
                    scope_id=dept_id,
                    title=g["title"],
                    metric=g.get("metric"),
                    target=g.get("target"),
                    priority=g.get("priority", 0),
                    progress=g.get("progress", 0.0),
                    parent_goal_id=company_goal_ids[0],
                )
    summary["goals"] = len(company_goal_ids) + sum(len(v) for v in DEPARTMENT_GOALS.values())

    # ── Budgets (company + department ceilings) ───────────────────────
    budget_mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 2000.0)
    for dept_id in dept_by_name.values():
        budget_mgr.ensure_budget(company.id, GoalScopeType.DEPARTMENT, dept_id, 600.0)
    summary["budgets"] = 1 + len(dept_by_name)

    # ── KPIs — idempotent by (company, name) ──────────────────────────
    for k in KPIS:
        existing = db.scalar(select(KPI).where(KPI.company_id == company.id, KPI.name == k["name"]))
        if existing is None:
            kpi_svc.create(
                company_id=company.id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company.id,
                name=k["name"],
                source_metric=k["source_metric"],
                target=k["target"],
                unit=k["unit"],
            )
            summary["kpis"] += 1
    kpi_svc.recompute_all(company.id)

    # ── Policies — idempotent by (scope, company, key) ────────────────
    for p in POLICIES:
        p_company_id = company.id if p["scope_type"] != PolicyScopeType.SYSTEM else None
        p_scope_id = company.id if p["scope_type"] == PolicyScopeType.COMPANY else None
        existing = db.scalar(
            select(Policy).where(
                Policy.scope_type == p["scope_type"],
                Policy.company_id == p_company_id,
                Policy.key == p["key"],
            )
        )
        if existing is None:
            policy_mgr.create(
                scope_type=p["scope_type"],
                company_id=p_company_id,
                scope_id=p_scope_id,
                name=p["name"],
                key=p["key"],
                value=p["value"],
            )
            summary["policies"] += 1

    # ── Risks — idempotent by (company, title) ────────────────────────
    for r in RISKS:
        existing = db.scalar(
            select(Risk).where(Risk.company_id == company.id, Risk.title == r["title"])
        )
        if existing is None:
            risk_mgr.create(
                company_id=company.id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company.id,
                title=r["title"],
                description=r["description"],
                severity=r["severity"],
                mitigation=r.get("mitigation"),
            )
            summary["risks"] += 1

    # ── Alerts + health (fresh snapshot) ──────────────────────────────
    from app.company.alerts import CompanyHealth

    summary["alerts"] += len(alert_mgr.generate_alerts(company.id))
    summary["health"] = CompanyHealth(db).explain(company.id)

    db.commit()
    return summary


def _print_summary(summary: dict[str, Any]) -> None:
    health = summary.get("health") or {}
    snap = health.get("health") if health else None
    print("\n=== NEXUS Labs seeded ===")
    print(f"company_id : {summary['company_id']}")
    print(f"departments: {len(summary['departments'])}")
    print(f"employees  : {len(summary['employees'])}")
    print(f"goals      : {summary.get('goals', 0)}")
    print(f"budgets    : {summary.get('budgets', 0)}")
    print(f"kpis       : {summary.get('kpis', 0)}")
    print(f"policies   : {summary.get('policies', 0)}")
    print(f"risks      : {summary.get('risks', 0)}")
    print(f"alerts     : {summary.get('alerts', 0)}")
    if snap:
        print(f"health     : {snap.get('status')} ({snap.get('overall_score')}/100)")
    print(
        "Verify with:\n"
        "  curl localhost:8000/api/v1/companies/\n"
        f"  curl localhost:8000/api/v1/companies/{summary['company_id']}/organization-chart"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the NEXUS Labs demo company.")
    parser.add_argument("--name", default="NEXUS Labs", help="Company name (default: NEXUS Labs)")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the company")
    args = parser.parse_args()

    # Ensure the schema exists before inserting.
    Base.metadata.create_all(bind=SessionLocal.kw["bind"])

    with SessionLocal() as db:
        summary = _seed_company(db, args.name, reset=args.reset)
        _print_summary(summary)


# Small facade so the seed can reuse departments without importing raw ORM.
class DepartmentManagerProxy:
    """Thin read/get-or-create over :class:`DepartmentManager`."""

    def __init__(self, db: Session, company_id: UUID) -> None:
        from app.company.departments import DepartmentManager

        self._db = db
        self._company_id = company_id
        self._mgr = DepartmentManager(db)

    def get_or_create(self, name: str, description: str | None = None) -> Department:
        existing = self._db.scalar(
            select(Department).where(
                Department.company_id == self._company_id,
                Department.name == name,
            )
        )
        if existing is not None:
            return existing
        return self._mgr.create(company_id=self._company_id, name=name, description=description)

    def all(self) -> list[Department]:
        return self._mgr.list_(self._company_id)


if __name__ == "__main__":
    main()
