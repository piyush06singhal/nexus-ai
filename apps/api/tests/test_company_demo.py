"""Tests for AI Company Layer — end-to-end company workflow integration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.agent import Agent
from app.db.models.company import AuthorityLevel, GoalScopeType
from app.db.models.employee import AIEmployee, EmployeeStatus


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="NEXUS Labs", industry="ai")


def _make_employee(db: Session, name: str, skills: list[str] | None = None):
    import json

    agent = Agent(name=f"{name}-agent", model_name="test")
    db.add(agent)
    db.flush()
    emp = AIEmployee(
        name=name.lower(),
        display_name=name,
        role="engineer",
        status=EmployeeStatus.ACTIVE,
        skills=json.dumps(skills or ["python"]),
        agent_id=agent.id,
    )
    db.add(emp)
    db.commit()
    return emp


class TestEndToEndCompanyWorkflow:
    """Full lifecycle: Company→Dept→Employee→Goal→Budget→KPI→Alert."""

    def test_company_lifecycle_with_departments(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.departments import DepartmentManager

        dm = DepartmentManager(db)
        eng = dm.create(company_id=company.id, name="Engineering", description="Build products")
        res = dm.create(company_id=company.id, name="Research", parent_department_id=eng.id)

        # Verify hierarchy
        children = dm.children(eng.id)
        assert res.id in [c.id for c in children]
        subtree = dm.subtree_ids(eng.id)
        assert res.id in subtree

    def test_membership_and_reporting(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.departments import DepartmentManager
        from app.company.membership import MembershipManager
        from app.company.roles import RoleManager

        dept = DepartmentManager(db).create(company_id=company.id, name="Eng")
        boss = _make_employee(db, "Boss")
        emp = _make_employee(db, "Alice")

        role = RoleManager(db).create(
            company_id=company.id,
            name="mgr",
            title="Manager",
            authority_level=AuthorityLevel.MANAGER,
        )
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=boss.id, department_id=dept.id, role_id=role.id)
        mm.add(company_id=company.id, employee_id=emp.id, department_id=dept.id, manager_id=boss.id)

        reports = mm.direct_reports(company.id, boss.id)
        assert emp.id in [r.employee_id for r in reports]

    def test_goal_progress_cascade(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.goals import GoalManager

        gm = GoalManager(db)
        parent = gm.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Ship v2",
            target=100.0,
        )
        child1 = gm.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Backend done",
            parent_goal_id=parent.id,
            target=50.0,
        )
        child2 = gm.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Frontend done",
            parent_goal_id=parent.id,
            target=50.0,
        )

        gm.recompute_progress(child1.id)
        gm.recompute_progress(child2.id)
        gm.recompute_progress(parent.id)

        updated_parent = gm.get(parent.id)
        assert updated_parent.progress >= 0.0

    def test_budget_reserve_and_spend(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.budget import BudgetManager

        bm = BudgetManager(db)
        budget = bm.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 1000.0)
        bm.spend(budget, cost=200.0, tokens=1000, tool_calls=5)
        snap = bm.snapshot(company.id, GoalScopeType.COMPANY, company.id)
        assert snap is not None
        assert snap.spent == 200.0
        assert snap.remaining == 800.0

    def test_kpi_recompute_from_sources(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.kpis import KPIService

        svc = KPIService(db)
        kpi = svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="Task Success",
            source_metric="task_success_rate",
            target=90.0,
            unit="%",
        )
        values = svc.recompute(kpi)
        # Empty company → 0 tasks → 0 success rate
        assert values.value == 0.0
        assert values.variance == -90.0

    def test_alert_generation(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.alerts import AlertManager

        am = AlertManager(db)
        alerts = am.generate_alerts(company.id)
        # Empty company may or may not generate alerts depending on thresholds
        assert isinstance(alerts, list)

    def test_decision_lifecycle(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.decisions import DecisionManager
        from app.company.membership import MembershipManager
        from app.company.roles import RoleManager

        ceo = _make_employee(db, "CEO")
        role = RoleManager(db).create(
            company_id=company.id,
            name="ceo",
            title="CEO",
            authority_level=AuthorityLevel.EXECUTIVE,
        )
        MembershipManager(db).add(company_id=company.id, employee_id=ceo.id, role_id=role.id)

        dm = DecisionManager(db)
        decision = dm.create(
            company_id=company.id,
            question="Should we adopt microservices?",
            options=[
                {"id": "opt-a", "label": "Adopt microservices"},
                {"id": "opt-b", "label": "Keep monolith"},
            ],
            context={"rationale": "Scale needs"},
            risk_level="medium",
        )
        dm.submit(decision.id)
        dm.approve(decision.id, reviewer_id=ceo.id, rationale="Approved by exec")
        dm.implement(decision.id, actor_id=ceo.id)
        updated = dm.get(decision.id)
        assert updated.status == "implemented"

    def test_risk_tracking(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.risks import RiskManager

        rm = RiskManager(db)
        risk = rm.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Vendor lock-in",
            severity="high",
        )
        from app.db.models.company import RiskStatus

        top = rm.top_risks(company.id)
        assert len(top) >= 1
        rm.update_status(risk.id, status=RiskStatus.MITIGATING)

    def test_report_generation_and_verify(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.reports import ReportGenerator

        gen = ReportGenerator(db)
        report = gen.generate(company.id, report_type="weekly")
        assert report.verification_status == "unverified"
        verified, summary = gen.verify(report)
        assert verified is True

    def test_analytics_full(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.analytics import AnalyticsService

        svc = AnalyticsService(db)
        result = svc.full_analytics(company.id)
        assert set(result.keys()) == {
            "workforce",
            "operations",
            "reliability",
            "finance",
            "strategy",
        }

    def test_company_health_explain(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.alerts import CompanyHealth

        health = CompanyHealth(db)
        result = health.compute(company.id)
        assert result["overall_score"] >= 0.0
        explanation = health.explain(company.id)
        assert "health" in explanation
        assert explanation["health"]["overall_score"] >= 0.0
        assert "explanations" in explanation

    def test_routing_with_multiple_candidates(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.membership import MembershipManager
        from app.company.roles import RoleManager
        from app.company.routing import OrgRoutingService

        role = RoleManager(db).create(
            company_id=company.id,
            name="eng",
            title="Eng",
        )
        mm = MembershipManager(db)
        for i in range(3):
            emp = _make_employee(db, f"Dev{i}", skills=["python", "ml"] if i == 0 else ["python"])
            mm.add(company_id=company.id, employee_id=emp.id, role_id=role.id)

        svc = OrgRoutingService(db)
        result = svc.route(
            company_id=company.id,
            task_name="Python task",
            required_skills=["python"],
        )
        # All three have "python"; the first (Dev0) also has "ml" for diversity bonus
        assert len(result["candidates"]) == 3
        assert result["selected_employee_id"] is not None

    def test_policy_resolution_across_scopes(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.policies import PolicyManager, PolicyResolver
        from app.db.models.company import PolicyScopeType

        pm = PolicyManager(db)
        pm.create(
            scope_type=PolicyScopeType.COMPANY,
            company_id=company.id,
            scope_id=company.id,
            name="Token Limit",
            key="max_tokens",
            value=4096,
        )
        resolver = PolicyResolver(db)
        value = resolver.effective("max_tokens", company_id=company.id)
        assert value == 4096

    def test_org_chart_structure(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.manager import CompanyManager

        mgr = CompanyManager(db)
        chart = mgr.organization_chart(company.id)
        assert chart.id is not None
        assert hasattr(chart, "children")
        assert chart.type in ("company", "department", "employee")

    def test_health_degradation_chain(self, db: Session) -> None:
        """§85: low verification rate → alert created → health degraded → explain."""
        from app.company.alerts import AlertManager, CompanyHealth
        from app.company.kpis import KPIService
        from app.company.membership import MembershipManager
        from app.db.models.company import (
            AlertSeverity,
            GoalScopeType,
        )
        from app.db.models.execution import AgentExecution, ExecutionStatus
        from app.db.models.reliability import (
            VerificationResult,
            VerificationRun,
            VerificationStatus,
        )
        from app.db.models.task import Task, TaskStatus

        # 1. Setup: company + employee with agent + membership + KPI
        company = _make_company(db)
        emp = _make_employee(db, "EngAgent", skills=["python", "ml"])
        MembershipManager(db).add(company_id=company.id, employee_id=emp.id)
        agent_id = emp.agent_id

        kpi_svc = KPIService(db)
        kpi = kpi_svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="Verification Rate",
            source_metric="verification_rate",
            target=90.0,
            unit="%",
        )

        # 2. Seed tasks, executions, verification runs/results — mostly FAIL
        #    10 verification results: 2 pass, 8 fail → 20% rate (well below 85%)
        task = Task(
            title="Test task",
            status=TaskStatus.COMPLETED,
            assigned_agent_id=agent_id,
        )
        db.add(task)
        db.flush()

        for i in range(10):
            execution = AgentExecution(
                task_id=task.id,
                agent_id=agent_id,
                status=ExecutionStatus.SUCCEEDED,
                latency_ms=100.0 + i,
            )
            db.add(execution)
            db.flush()

            run = VerificationRun(
                execution_id=execution.id,
                task_id=task.id,
                status=VerificationStatus.PASS,
                score=0.9,
            )
            db.add(run)
            db.flush()

            result_status = VerificationStatus.PASS if i < 2 else VerificationStatus.FAIL
            result = VerificationResult(
                run_id=run.id,
                execution_id=execution.id,
                status=result_status,
                score=0.9 if result_status == VerificationStatus.PASS else 0.2,
                confidence=0.8,
            )
            db.add(result)
        db.commit()

        # 3. Recompute KPI → should show low verification rate
        reading = kpi_svc.recompute(kpi)
        assert reading.value == 20.0, f"Expected 20%, got {reading.value}%"
        assert reading.variance < 0  # below target

        # 4. Generate alerts → should create a reliability alert
        alerts = AlertManager(db).generate_alerts(company.id)
        reliability_alerts = [a for a in alerts if a.category == "reliability"]
        assert len(reliability_alerts) >= 1, "Expected at least one reliability alert"
        assert reliability_alerts[0].severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL)
        assert "below threshold" in reliability_alerts[0].title.lower()

        # 5. Health score should be degraded (quality dimension low)
        health_svc = CompanyHealth(db)
        health = health_svc.compute(company.id)
        assert health["overall_score"] < 80, "Health should be degraded"
        assert health["status"] in ("degraded", "critical")
        assert health["dimensions"]["quality"] < 50

        # 6. Explanation should flag quality as degraded
        explanation = health_svc.explain(company.id)
        assert "quality" in explanation["explanations"]
        assert "degraded" in explanation["explanations"]["quality"]

    def test_weekly_operating_cycle(self, db: Session) -> None:
        """§84: weekly cycle → collect KPIs → report → verify → alerts."""
        from app.company.alerts import AlertManager
        from app.company.kpis import KPIService
        from app.company.reports import ReportGenerator
        from app.db.models.company import GoalScopeType

        company = _make_company(db)

        # Seed a few KPIs
        svc = KPIService(db)
        svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="Task Success",
            source_metric="task_success_rate",
            target=90.0,
            unit="%",
        )

        # Recompute all KPIs
        readings = svc.recompute_all(company.id)
        assert len(readings) == 1

        # Generate a weekly report
        gen = ReportGenerator(db)
        report = gen.generate(company.id, report_type="weekly")
        assert report.verification_status == "unverified"

        # Verify the report
        verified, _ = gen.verify(report)
        assert verified is True

        # Check for alerts (empty company won't trigger, but function should not error)
        alerts = AlertManager(db).generate_alerts(company.id)
        assert isinstance(alerts, list)

    def test_goal_to_risk_chain(self, db: Session) -> None:
        """§83: goal → progress update → risk created → risk tracked."""
        from app.company.goals import GoalManager
        from app.company.risks import RiskManager
        from app.db.models.company import GoalScopeType, RiskStatus

        company = _make_company(db)

        # Create a company goal
        gm = GoalManager(db)
        goal = gm.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Ship competitive analysis",
            priority=30,
        )
        assert goal.progress == 0.0

        # Update progress
        gm.update(goal.id, progress=0.35)
        updated = gm.get(goal.id)
        assert updated.progress == 0.35

        # Create a risk tracking the goal
        rm = RiskManager(db)
        risk = rm.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Analysis may miss key competitors",
            severity="medium",
            mitigation="Cross-check with market research",
        )
        assert risk.status == RiskStatus.OPEN

        # Top risks should include this one
        top = rm.top_risks(company.id)
        assert risk.id in [r.id for r in top]
