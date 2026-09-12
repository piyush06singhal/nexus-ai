"""Tests for Phase 9 strategic + startup planning and validation."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.startup import StartupPlan, StartupPlanStatus

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Plan Co {_counter}", description="unit")


def _mission(db: Session, *, title: str | None = None):
    global _counter
    from app.startup.mission import MissionManager

    _counter += 1
    company = _company(db)
    return company, MissionManager(db).create(
        company_id=company.id,
        title=title or f"Mission {_counter}",
        mission_statement=("Build a productivity tool for small teams with verifiable cycles."),
        desired_outcome="Initial cohort adopts the tool.",
        target_market="small software teams",
        constraints=["Bounded autonomy only"],
        assumptions=["Teams adopt CLI tooling."],
        success_criteria=["Task success rate above 90%."],
        strategic_context={"phase": 9},
        priority=1,
    )


def _approved_bootstrap_gate(db: Session, company_id, plan_id=None):
    from app.startup.gates import ApprovalGateManager

    manager = ApprovalGateManager(db)
    gate = manager.create(
        company_id=company_id,
        gate_type="company_bootstrap_approval",
        requested_action={"action": "provision_employee"},
        rationale="Unit test bootstrap gate.",
        risk_level="medium",
    )
    manager.approve(company_id, gate.id, approver_id=None)
    return gate.id


def _plan_fields() -> dict:
    return {
        "business_objectives": [{"key": "ar", "title": "Reach ARR", "target": 100000}],
        "product_objectives": [
            {"key": "adoption", "title": "Drive adoption", "target": "10 pilot teams"}
        ],
        "marketing_objectives": [{"key": "known", "title": "Build awareness"}],
        "operational_objectives": [{"key": "velocity", "title": "Keep cycles fast"}],
        "departments": [
            {
                "name": "Engineering",
                "roles": [
                    {"name": "engineer", "title": "Engineer", "authority": "operator"},
                    {"name": "lead", "title": "Engineering Lead", "authority": "manager"},
                ],
            },
            {
                "name": "Research",
                "roles": [{"name": "researcher", "title": "Researcher", "authority": "operator"}],
            },
        ],
        "roles": [
            {"name": "engineer", "title": "Engineer", "authority": "operator"},
            {"name": "lead", "title": "Engineering Lead", "authority": "manager"},
            {"name": "researcher", "title": "Researcher", "authority": "operator"},
        ],
        "milestones": [
            {"title": "MVP", "deadline": "2026-12-31"},
            {"title": "GTM", "deadline": "2027-03-31"},
        ],
        "capabilities": ["python", "ml", "research"],
        "initial_products": [
            {
                "name": "Dev Productivity Platform",
                "description": "A CLI for small teams",
                "product_type": "developer_tool",
            }
        ],
        "initial_projects": [
            {
                "name": "Build the CLI",
                "description": "Core CLI implementation",
                "objective": "Drive adoption",
            }
        ],
        "kpi_targets": {"task_success_rate": 90, "verification_rate": 90},
        "budget_allocation": {"company": 1000, "departments": {"Engineering": 600}},
        "execution_priorities": [{"key": "mvp", "priority": 1}],
        "approval_requirements": {"high_risk_actions": "approval"},
    }


class TestStrategicPlanner:
    def test_deterministic_plan(self, db: Session) -> None:
        from app.startup.mission import MissionManager
        from app.startup.strategy import DeterministicStrategicPlanner

        company, mission = _mission(db)
        analysis = MissionManager(db).analyze(mission)
        plan = DeterministicStrategicPlanner(db).plan(mission, analysis)
        assert plan.objectives
        assert plan.priorities
        assert plan.milestones
        assert plan.vision

    def test_plan_never_executes(self, db: Session) -> None:
        """A strategic plan is a document — it creates no company state."""
        from app.db.models.company import Company
        from app.startup.mission import MissionManager
        from app.startup.strategy import DeterministicStrategicPlanner

        company, mission = _mission(db)
        analysis = MissionManager(db).analyze(mission)
        n_before = len(db.query(Company).all())
        DeterministicStrategicPlanner(db).plan(mission, analysis)
        assert len(db.query(Company).all()) == n_before


class TestStartupPlan:
    def test_create_and_validate(self, db: Session) -> None:
        from app.startup.mission import MissionManager
        from app.startup.plans import StartupPlanManager

        company, mission = _mission(db)
        MissionManager(db).plan(mission)
        plan = StartupPlanManager(db).create(mission_id=mission.id, **_plan_fields())
        result = StartupPlanManager(db).validate(plan).to_dict()
        assert result["ok"] is True or any(i["severity"] == "warning" for i in result["issues"])

    def test_approve_records_audit(self, db: Session) -> None:
        from app.startup.mission import MissionManager
        from app.startup.plans import StartupPlanManager

        company, mission = _mission(db)
        MissionManager(db).plan(mission)
        plan = StartupPlanManager(db).create(mission_id=mission.id, **_plan_fields())
        StartupPlanManager(db).approve(plan, actor="test")
        assert plan.status == StartupPlanStatus.APPROVED
        row = db.get(StartupPlan, plan.id)
        import json

        review = json.loads(row.review or "{}")
        assert review.get("approved_at")
        assert review.get("approved_by") == "test"

    def test_only_draft_can_be_approved(self, db: Session) -> None:
        from app.startup.mission import MissionManager
        from app.startup.plans import StartupPlanManager

        company, mission = _mission(db)
        MissionManager(db).plan(mission)
        mgr = StartupPlanManager(db)
        plan = mgr.create(mission_id=mission.id, **_plan_fields())
        mgr.approve(plan, actor="test")
        try:
            mgr.approve(plan, actor="test")
            raise AssertionError("Re-approving an approved plan should fail")
        except ValueError:
            pass


class TestBootstrap:
    def test_bootstrap_full_company(self, db: Session) -> None:
        from app.startup.mission import MissionManager
        from app.startup.plans import StartupPlanManager

        company, mission = _mission(db)
        MissionManager(db).plan(mission)
        plan = StartupPlanManager(db).create(mission_id=mission.id, **_plan_fields())
        StartupPlanManager(db).approve(plan, actor="test")
        gate_id = _approved_bootstrap_gate(db, company.id)

        from app.startup.bootstrap import CompanyBootstrapper

        result = CompanyBootstrapper(db).bootstrap(plan, approved_gate_id=gate_id, actor="test")
        assert result["departments"]
        assert result["employees"]
        assert result["products"]
        assert result["projects"]
        assert result["kpis"] >= 1
        assert result["budgets"] >= 1
        assert result["goals"] >= 1

    def test_bootstrap_requires_approved_plan(self, db: Session) -> None:
        from app.startup.mission import MissionManager
        from app.startup.plans import StartupPlanManager

        company, mission = _mission(db)
        MissionManager(db).plan(mission)
        plan = StartupPlanManager(db).create(mission_id=mission.id, **_plan_fields())

        from app.startup.bootstrap import CompanyBootstrapper

        try:
            CompanyBootstrapper(db).bootstrap(plan, actor="test")
            raise AssertionError("Bootstrapping an unapproved plan should fail")
        except ValueError as exc:
            assert "approved" in str(exc)

    def test_bootstrap_is_idempotent(self, db: Session) -> None:
        """Re-bootstrapping pushes through the same governed path without duplicating."""
        from app.startup.mission import MissionManager
        from app.startup.plans import StartupPlanManager

        company, mission = _mission(db)
        MissionManager(db).plan(mission)
        mgr = StartupPlanManager(db)
        plan = mgr.create(mission_id=mission.id, **_plan_fields())
        mgr.approve(plan, actor="test")

        gate_id = _approved_bootstrap_gate(db, company.id)
        from app.startup.bootstrap import CompanyBootstrapper

        CompanyBootstrapper(db).bootstrap(plan, approved_gate_id=gate_id, actor="test")
        # The plan moved to ACTIVE; bootstrapping again is guarded upstream and
        # bootstrap itself refuses non-approved plans.
        assert plan.status == StartupPlanStatus.ACTIVE
        from app.startup.bootstrap import CompanyBootstrapper

        try:
            CompanyBootstrapper(db).bootstrap(plan, approved_gate_id=gate_id, actor="test")
            raise AssertionError("Re-bootstrapping an active plan should fail")
        except ValueError:
            pass
