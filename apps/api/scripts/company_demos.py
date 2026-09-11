"""Company Layer demos (§82–§85).

Three self-contained demo functions that exercise the real Company Layer
services end-to-end.  Each can be called from tests, the API, or as a
standalone script.

Run from ``apps/api``::

    .venv/bin/python -m scripts.company_demos goal_demo
    .venv/bin/python -m scripts.company_demos weekly_cycle_demo
    .venv/bin/python -m scripts.company_demos health_degradation_demo

All data lives in the same Postgres/SQLite database the rest of NEXUS uses.
"""

from __future__ import annotations

import json
import sys
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

# Ensure ``app`` resolves when run as a script inside apps/api.
sys.path.insert(0, ".")  # noqa: E402

from app.db.models import (  # noqa: E402
    Agent,
    AIEmployee,
    EmployeeStatus,
    GoalScopeType,
)
from app.db.session import SessionLocal  # noqa: E402

# ── Helpers ────────────────────────────────────────────────────────────────────


def _emp(db: Session, company_id: UUID, name: str, skills: list[str]) -> AIEmployee:
    """Create an employee with an auto-created agent (idempotent by name)."""
    from sqlalchemy import select

    existing = db.scalar(select(AIEmployee).where(AIEmployee.name == name.lower()))
    if existing is not None:
        return existing

    agent = Agent(name=f"{name}-demo-agent", model_name="test")
    db.add(agent)
    db.flush()
    emp = AIEmployee(
        name=name.lower(),
        display_name=name,
        role="engineer",
        status=EmployeeStatus.ACTIVE,
        skills=json.dumps(skills),
        agent_id=agent.id,
    )
    db.add(emp)
    db.flush()
    return emp


def _dept(db: Session, company_id: UUID, name: str) -> Any:
    """Get or create a department."""
    from sqlalchemy import select

    from app.company.departments import DepartmentManager
    from app.db.models.company import Department

    existing = db.scalar(
        select(Department).where(Department.company_id == company_id, Department.name == name)
    )
    if existing is not None:
        return existing
    return DepartmentManager(db).create(
        company_id=company_id, name=name, description=f"{name} department"
    )


def _company(db: Session, name: str) -> Any:
    """Get or create a company by name (idempotent)."""
    from sqlalchemy import select

    from app.company.manager import CompanyManager
    from app.db.models.company import Company

    existing = db.scalar(select(Company).where(Company.name == name))
    if existing is not None:
        return existing
    return CompanyManager(db).create(name=name)


def _goal(
    db: Session,
    company_id: UUID,
    scope_type: GoalScopeType,
    scope_id: UUID,
    title: str,
    **kwargs: Any,
) -> Any:
    """Get or create a goal by (company, scope, title) — idempotent."""
    from sqlalchemy import select

    from app.company.goals import GoalManager
    from app.db.models.company import OrgGoal

    existing = db.scalar(
        select(OrgGoal).where(
            OrgGoal.company_id == company_id,
            OrgGoal.scope_type == scope_type,
            OrgGoal.scope_id == scope_id,
            OrgGoal.title == title,
        )
    )
    if existing is not None:
        return existing
    return GoalManager(db).create(
        company_id=company_id,
        scope_type=scope_type,
        scope_id=scope_id,
        title=title,
        **kwargs,
    )


def _kpi(db: Session, company_id: UUID, name: str, source_metric: str, **kwargs: Any) -> Any:
    """Get or create a KPI by (company, name) — idempotent."""
    from sqlalchemy import select

    from app.company.kpis import KPIService
    from app.db.models.company import KPI

    existing = db.scalar(select(KPI).where(KPI.company_id == company_id, KPI.name == name))
    if existing is not None:
        return existing
    return KPIService(db).create(
        company_id=company_id,
        scope_type=GoalScopeType.COMPANY,
        scope_id=company_id,
        name=name,
        source_metric=source_metric,
        **kwargs,
    )


def _membership(
    db: Session, company_id: UUID, emp: AIEmployee | UUID, dept_id: UUID | None = None
) -> None:
    """Add employee (object or id) to company (idempotent)."""
    from sqlalchemy import select

    from app.company.membership import MembershipManager
    from app.db.models.company import OrganizationalMembership

    emp_id = emp if isinstance(emp, UUID) else emp.id
    existing = db.scalar(
        select(OrganizationalMembership).where(
            OrganizationalMembership.company_id == company_id,
            OrganizationalMembership.employee_id == emp_id,
        )
    )
    if existing is not None:
        return
    MembershipManager(db).add(
        company_id=company_id,
        employee_id=emp_id,
        department_id=dept_id,
    )


# ── §83  Company Goal Demo ─────────────────────────────────────────────────────


def goal_demo(db: Session | None = None) -> dict[str, Any]:
    """Demonstrate a company goal flow end-to-end (§83).

    Creates a "Prepare competitive analysis" company goal, creates the
    Research department and analyst, routes a task, and shows the full
    lifecycle: goal → department → employee → progress.

    Returns a summary dict.
    """
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        from app.company.goals import GoalManager
        from app.company.kpis import KPIService

        company = _company(db, "Goal Demo Co")

        # Departments
        _dept(db, company.id, "Engineering")
        research = _dept(db, company.id, "Research")

        # Employees
        researcher = _emp(db, company.id, "Researcher", ["research", "analysis", "writing"])
        _membership(db, company.id, researcher, research.id)

        # Company goal
        goal = _goal(
            db,
            company.id,
            GoalScopeType.COMPANY,
            company.id,
            "Prepare competitive analysis report",
            metric="report_ready",
            target="1 report published",
            priority=30,
        )

        # Department goal aligned to company goal
        dept_goal = _goal(
            db,
            company.id,
            GoalScopeType.DEPARTMENT,
            research.id,
            "Draft competitive landscape analysis",
            metric="sections_drafted",
            target="5 sections",
            priority=25,
            parent_goal_id=goal.id,
        )

        # Simulate progress
        gm = GoalManager(db)
        gm.update(dept_goal.id, progress=0.6)
        gm.recompute_progress(goal.id)

        # Create verification KPI (idempotent) and recompute all
        _kpi(
            db,
            company.id,
            "Goal Progress",
            "goal_progress",
            target=100.0,
            unit="%",
        )
        KPIService(db).recompute_all(company.id)

        db.commit()

        goal_refreshed = gm.get(goal.id)
        summary = {
            "demo": "goal_demo (§83)",
            "company_id": str(company.id),
            "company_goal": goal.title,
            "dept_goal": dept_goal.title,
            "dept_progress": dept_goal.progress,
            "company_progress": goal_refreshed.progress,
            "status": goal_refreshed.status.value,
        }
        return summary
    finally:
        if own_db:
            db.close()


# ── §84  Weekly Operating Cycle Demo ───────────────────────────────────────────


def weekly_cycle_demo(db: Session | None = None) -> dict[str, Any]:
    """Demonstrate a weekly operating cycle (§84).

    Collects KPI metrics, generates a report, verifies it, and checks for
    alerts.  This mirrors what a scheduled weekly workflow would do.

    Returns a summary dict.
    """
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        from app.company.alerts import AlertManager
        from app.company.budget import BudgetManager
        from app.company.kpis import KPIService
        from app.company.reports import ReportGenerator

        company = _company(db, "Weekly Cycle Demo Co")

        # Seed budget + goal so the report has data
        BudgetManager(db).ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 5000.0)
        _goal(
            db,
            company.id,
            GoalScopeType.COMPANY,
            company.id,
            "Ship Q3 release",
            priority=30,
            progress=0.45,
        )

        # 1. Collect KPI metrics (idempotent by name)
        kpi_svc = KPIService(db)
        for name, metric, target in [
            ("Task Success", "task_success_rate", 90.0),
            ("Verification", "verification_rate", 85.0),
            ("Budget Use", "budget_utilization", 80.0),
            ("Goal Progress", "goal_progress", 100.0),
        ]:
            _kpi(db, company.id, name, metric, target=target, unit="%")
        readings = kpi_svc.recompute_all(company.id)

        # 2. Generate report
        gen = ReportGenerator(db)
        report = gen.generate(company.id, report_type="weekly")

        # 3. Verify report
        verified, summary_text = gen.verify(report)

        # 4. Check alerts
        alerts = AlertManager(db).generate_alerts(company.id)

        db.commit()

        return {
            "demo": "weekly_cycle_demo (§84)",
            "company_id": str(company.id),
            "kpis_recomputed": len(readings),
            "report_type": report.report_type,
            "report_verified": verified,
            "verification_summary": summary_text[:120] if summary_text else None,
            "alerts_generated": len(alerts),
        }
    finally:
        if own_db:
            db.close()


# ── §85  Health Degradation Demo ───────────────────────────────────────────────


def health_degradation_demo(db: Session | None = None) -> dict[str, Any]:
    """Demonstrate health degradation detection (§85).

    Creates a company with an employee, seeds verification results that are
    mostly failures, then runs alert generation + health scoring to show the
    degradation chain: low verification → alert → degraded health → explanation.

    Returns a summary dict.
    """
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        from app.company.alerts import AlertManager, CompanyHealth
        from app.company.kpis import KPIService
        from app.db.models.execution import AgentExecution, ExecutionStatus
        from app.db.models.reliability import (
            VerificationResult,
            VerificationRun,
            VerificationStatus,
        )
        from app.db.models.task import Task, TaskStatus

        company = _company(db, "Health Demo Co")

        # Employee with agent
        emp = _emp(db, company.id, "EngAgent", ["python", "ml"])
        _membership(db, company.id, emp.id)
        agent_id = emp.agent_id

        # Seed KPI (idempotent)
        kpi_svc = KPIService(db)
        kpi = _kpi(
            db,
            company.id,
            "Verification Rate",
            "verification_rate",
            target=90.0,
            unit="%",
        )

        # Seed tasks + executions + verification results (2 pass, 8 fail)
        # Only seed degradation data once per company; idempotent re-runs
        # reuse the existing verification results so the rate stays stable.
        from sqlalchemy import func, select

        existing_total = db.scalar(
            select(func.count(VerificationResult.id))
            .join(
                AgentExecution,
                AgentExecution.id == VerificationResult.execution_id,
            )
            .where(AgentExecution.agent_id == agent_id)
        )
        if existing_total == 0:
            task = Task(title="Demo task", status=TaskStatus.COMPLETED, assigned_agent_id=agent_id)
            db.add(task)
            db.flush()

            for i in range(10):
                exec_ = AgentExecution(
                    task_id=task.id,
                    agent_id=agent_id,
                    status=ExecutionStatus.SUCCEEDED,
                    latency_ms=100.0 + i,
                )
                db.add(exec_)
                db.flush()

                run = VerificationRun(
                    execution_id=exec_.id,
                    task_id=task.id,
                    status=VerificationStatus.PASS,
                    score=0.9,
                )
                db.add(run)
                db.flush()

                vstatus = VerificationStatus.PASS if i < 2 else VerificationStatus.FAIL
                db.add(
                    VerificationResult(
                        run_id=run.id,
                        execution_id=exec_.id,
                        status=vstatus,
                        score=0.9 if vstatus == VerificationStatus.PASS else 0.2,
                        confidence=0.8,
                    )
                )
            db.commit()

        # Recompute KPI
        reading = kpi_svc.recompute(kpi)

        # Generate alerts
        alerts = AlertManager(db).generate_alerts(company.id)
        reliability_alerts = [a for a in alerts if a.category == "reliability"]

        # Health
        health_svc = CompanyHealth(db)
        health = health_svc.compute(company.id)
        explanation = health_svc.explain(company.id)

        return {
            "demo": "health_degradation_demo (§85)",
            "company_id": str(company.id),
            "verification_rate": reading.value,
            "verification_target": kpi.target,
            "verification_variance": reading.variance,
            "reliability_alerts": len(reliability_alerts),
            "health_status": health["status"],
            "health_score": health["overall_score"],
            "quality_dimension": health["dimensions"]["quality"],
            "quality_explanation": explanation["explanations"].get("quality"),
            "all_explanations": explanation["explanations"],
        }
    finally:
        if own_db:
            db.close()


# ── CLI ────────────────────────────────────────────────────────────────────────

DEMOS = {
    "goal_demo": goal_demo,
    "weekly_cycle_demo": weekly_cycle_demo,
    "health_degradation_demo": health_degradation_demo,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in DEMOS:
        print(f"Usage: python -m scripts.company_demos <{' | '.join(DEMOS)}>")
        sys.exit(1)

    name = sys.argv[1]
    demo_fn = DEMOS[name]
    result = demo_fn()
    print(f"\n=== {name} ===")
    for k, v in result.items():
        if k == "all_explanations" and isinstance(v, dict):
            print(f"  {k}:")
            for dim, text in v.items():
                print(f"    {dim}: {text}")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
