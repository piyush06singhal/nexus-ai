"""Tests for Phase 9 workforce planning and governed employee provisioning."""

from __future__ import annotations

from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Workforce Co {_counter}", description="unit")


def _plan(db: Session):
    global _counter
    from app.startup.plans import StartupPlanManager

    _counter += 1
    company = _company(db)
    mission = _planned_mission(db, company)
    plan = StartupPlanManager(db).create(
        mission_id=mission.id,
        business_objectives=[{"key": "ar", "title": "Reach ARR"}],
        product_objectives=[{"key": "adopt", "title": "Adopt"}],
        departments=[
            {
                "name": "Engineering",
                "roles": [{"name": "engineer", "title": "Engineer", "authority": "operator"}],
            }
        ],
        roles=[{"name": "engineer", "title": "Engineer", "authority": "operator"}],
        milestones=[{"title": "MVP"}],
        initial_products=[{"name": "Tool", "description": "A tool"}],
        initial_projects=[{"name": "Build", "description": "Build it"}],
        kpi_targets={"task_success_rate": 90},
        budget_allocation={"company": 500},
    )
    return company, plan


def _planned_mission(db: Session, company):
    from app.startup.mission import MissionManager

    return MissionManager(db).create(
        company_id=company.id,
        title=f"Mission {_counter}",
        mission_statement="Build a tool for small teams.",
        desired_outcome="Adoption.",
        target_market="small teams",
        constraints=["Bounded autonomy only"],
        assumptions=["Adoption."],
        success_criteria=["90% task success."],
    )


def _approved_gate(db: Session, company_id):
    from app.startup.gates import ApprovalGateManager

    manager = ApprovalGateManager(db)
    gate = manager.create(
        company_id=company_id,
        gate_type="workforce_approval",
        requested_action={"action": "provision_employee"},
        rationale="Unit test gate",
        risk_level="low",
    )
    manager.approve(company_id, gate.id, approver_id=None)
    return gate.id


class TestWorkforcePlanner:
    def test_plan_demand_from_blueprint(self, db: Session) -> None:
        from app.startup.workforce import WorkforcePlanner

        company, plan = _plan(db)
        demand = WorkforcePlanner(db).plan(plan)
        assert demand
        roles = {d.role for d in demand}
        assert "engineer" in roles
        assert all(d.count >= 1 for d in demand)
        assert all(d.department for d in demand)

    def test_plan_exposes_max_employees(self, db: Session) -> None:
        from app.startup.workforce import WorkforcePlanner

        assert WorkforcePlanner(db).max_employees > 0

    def test_persist_writes_workforce_plan(self, db: Session) -> None:
        from app.db.models.startup import WorkforcePlan
        from app.startup.workforce import WorkforcePlanner

        company, plan = _plan(db)
        demand = WorkforcePlanner(db).plan(plan)
        row = WorkforcePlanner(db).persist(plan, demand)
        stored = db.get(WorkforcePlan, row.id)
        assert stored is not None
        assert stored.demand


class TestProvisioning:
    def test_provision_requires_approval_gate(self, db: Session) -> None:
        from app.startup.provision import EmployeeProvisioner
        from app.startup.workforce import WorkforcePlanner

        company, plan = _plan(db)
        demand = WorkforcePlanner(db).plan(plan)
        try:
            EmployeeProvisioner(db).provision(company_id=company.id, demand=demand, actor="test")
            raise AssertionError("Provisioning without a gate at bounded_autonomy must fail")
        except Exception as exc:
            assert "approval" in str(exc).lower()

    def test_provision_creates_employees(self, db: Session) -> None:
        from app.startup.provision import EmployeeProvisioner
        from app.startup.workforce import WorkforcePlanner

        company, plan = _plan(db)
        gate_id = _approved_gate(db, company.id)
        demand = WorkforcePlanner(db).plan(plan)
        provisioned = EmployeeProvisioner(db).provision(
            company_id=company.id,
            demand=demand,
            approved_gate_id=gate_id,
            actor="test",
        )
        assert provisioned
        # Each provisioned record has an employee id backed by a real row.
        from uuid import UUID

        from app.db.models.employee import AIEmployee

        for record in provisioned:
            emp_id = record.get("employee_id")
            assert emp_id is not None
            assert db.get(AIEmployee, UUID(str(emp_id))) is not None

    def test_provision_caps_at_max_employees(self, db: Session) -> None:
        from app.startup.provision import EmployeeProvisioner
        from app.startup.workforce import WorkforcePlanner

        company, plan = _plan(db)
        gate_id = _approved_gate(db, company.id)
        planner = WorkforcePlanner(db)
        demand = planner.plan(plan)
        # Scale demand well past the cap.
        demand = [d.__class__(**{**d.__dict__, "count": 999}) for d in demand]
        try:
            EmployeeProvisioner(db).provision(
                company_id=company.id,
                demand=demand,
                approved_gate_id=gate_id,
                actor="test",
            )
            raise AssertionError("Provisioning past MAX_AUTONOMOUS_EMPLOYEES must fail")
        except ValueError:
            pass

    def test_provision_from_workforce_plan(self, db: Session) -> None:
        from app.startup.provision import EmployeeProvisioner
        from app.startup.workforce import WorkforcePlanner

        company, plan = _plan(db)
        demand = WorkforcePlanner(db).plan(plan)
        workforce = WorkforcePlanner(db).persist(plan, demand)
        gate_id = _approved_gate(db, company.id)
        provisioned = EmployeeProvisioner(db).provision_from_workforce_plan(
            company_id=company.id,
            workforce_plan=workforce,
            approved_gate_id=gate_id,
            actor="test",
        )
        assert provisioned
