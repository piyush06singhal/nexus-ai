"""Phase 9 security tests — cross-company isolation and authorization.

Every Phase 9 entity is company-scoped; an approved approval gate from one
company must never authorize (or even be readable on) another company, and the
hard never-autonomous boundary holds at every autonomy level. These tests
assert isolation of missions/graphs/gates/feedback/policies and that bypass
attempts (cross-company gates, unaudited budget allocation, replan under a
foreign gate) are blocked.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Secure Co {_counter}", description="unit")


def _budgeted(db: Session, *, limit: float = 1000.0):
    from app.company.budget import BudgetManager
    from app.db.models.company import GoalScopeType

    company = _company(db)
    BudgetManager(db).ensure_budget(
        company.id,
        GoalScopeType.COMPANY,
        company.id,
        monthly_limit=limit,
    )
    return company


def _approved_gate(db: Session, company_id, gate_type: str = "budget_approval"):
    from app.startup.gates import ApprovalGateManager

    manager = ApprovalGateManager(db)
    gate = manager.create(
        company_id=company_id,
        gate_type=gate_type,
        requested_action={"action": "allocate_budget"},
        rationale="Unit test gate.",
        risk_level="medium",
    )
    manager.approve(company_id, gate.id, approver_id=None)
    return gate.id


class TestCrossCompanyIsolation:
    def test_mission_never_leaks(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        company_a = _company(db)
        company_b = _company(db)
        mission = MissionManager(db).create(
            company_id=company_a.id,
            title="Secret mission",
            mission_statement="Classified.",
        )
        assert MissionManager(db).get(company_b.id, mission.id) is None
        assert MissionManager(db).list_(company_b.id) == []

    def test_gate_never_readable_across_companies(self, db: Session) -> None:
        from app.startup.gates import ApprovalGateManager

        company_a = _company(db)
        company_b = _company(db)
        mgr = ApprovalGateManager(db)
        gate = mgr.create(
            company_id=company_a.id,
            gate_type="high_risk_action_approval",
            requested_action={"action": "replan"},
            rationale="A's gate",
        )
        # Can't read, list, approve, or reject a foreign gate.
        assert mgr.get(company_b.id, gate.id) is None
        assert mgr.get(company_a.id, gate.id) is not None
        assert gate.id not in [g.id for g in mgr.list_(company_b.id)]

    def test_autonomy_policy_isolated(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService

        company_a = _company(db)
        company_b = _company(db)
        AutonomyService(db).set_policy(company_a.id, autonomy_level="manual")
        assert AutonomyService(db).get_policy(company_a.id).autonomy_level.value == "manual"
        # Company B keeps its own default, untouched.
        assert AutonomyService(db).get_policy(company_b.id).autonomy_level.value == (
            "bounded_autonomy"
        )

    def test_feedback_isolated(self, db: Session) -> None:
        from app.startup.feedback import FeedbackService
        from app.startup.types import FeedbackRecord

        company_a = _company(db)
        company_b = _company(db)
        FeedbackService(db).record(
            company_a.id,
            FeedbackRecord(
                category="risk_exposure",
                observation="A's signal",
                source="test",
                confidence=0.5,
            ),
        )
        assert len(FeedbackService(db).list_(company_a.id)) == 1
        assert FeedbackService(db).list_(company_b.id) == []

    def test_graph_isolated(self, db: Session) -> None:
        from uuid import UUID

        from app.db.models.startup import MissionGraphRelation
        from app.startup.graph import MissionGraphBuilder

        company_a = _company(db)
        company_b = _company(db)
        builder = MissionGraphBuilder(db)
        builder.link(
            company_id=company_a.id,
            source_type="goal",
            source_id=UUID(int=1),
            target_type="mission",
            target_id=UUID(int=2),
            relation=MissionGraphRelation.DERIVED_FROM,
        )
        assert builder.query(company_a.id)
        assert builder.query(company_b.id) == []


class TestAuthorization:
    def test_foreign_gate_cannot_authorize_provision(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ApprovalRequiredError

        company_a = _company(db)
        company_b = _company(db)
        # A gate approved on company A must not authorize an action on company B.
        gate_a = _approved_gate(db, company_a.id)
        try:
            AutonomyService(db).enforce("allocate_budget", company_b.id, approved_gate_id=gate_a)
            raise AssertionError("A foreign approved gate must not authorize")
        except ApprovalRequiredError:
            pass

    def test_budget_allocation_requires_owned_gate(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision, ApprovalRequiredError

        company = _budgeted(db, limit=1000.0)
        decision, _ = AutonomyService(db).decision(
            "allocate_budget", company.id, estimated_cost=5000.0
        )
        assert decision == ActionDecision.REQUIRE_APPROVAL
        try:
            AutonomyService(db).enforce("allocate_budget", company.id, estimated_cost=5000.0)
            raise AssertionError("Budget allocation without a gate must raise")
        except ApprovalRequiredError:
            pass
        # An owned, approved gate satisfies the authorization.
        gate = _approved_gate(db, company.id)
        assert (
            AutonomyService(db).enforce(
                "allocate_budget",
                company.id,
                estimated_cost=5000.0,
                approved_gate_id=gate,
            )
            == ActionDecision.ALLOW
        )

    def test_replan_under_foreign_gate_blocked(self, db: Session) -> None:
        from app.startup.projects import ProjectManager
        from app.startup.replan import ReplanningEngine
        from app.startup.types import ApprovalRequiredError, ReplanDecision, ReplanResponse

        company_a = _company(db)
        company_b = _company(db)
        project = ProjectManager(db).create(
            company_id=company_b.id,
            name="Secret",
            priority=1,
            status="active",
        )
        decision = ReplanDecision(
            trigger="kpi_underperformance",
            response=ReplanResponse.REPRIORITIZE,
            reason="rep",
            actions=[
                {"kind": "reprioritize_project", "project_id": str(project.id), "priority": 0}
            ],
            requires_approval=True,
        )
        # An approved gate on A cannot authorize a replan on B.
        gate_a = _approved_gate(db, company_a.id, "high_risk_action_approval")
        try:
            ReplanningEngine(db).apply(
                company_id=company_b.id,
                decision=decision,
                approved_gate_id=gate_a,
            )
            raise AssertionError("Replan under a foreign gate must be blocked")
        except ApprovalRequiredError:
            pass
        # The project was not reprioritized.
        assert ProjectManager(db).get(company_b.id, project.id).priority == 1

    def test_never_allowed_blocked_even_at_high_autonomy(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision

        company = _company(db)
        AutonomyService(db).set_policy(company.id, autonomy_level="high_autonomy")
        svc = AutonomyService(db)
        for action in (
            "finance",
            "legal",
            "hire_human",
            "fire_employee",
            "self_modify",
            "external_publish",
            "browser_automation",
            "computer_use",
            "payment_processing",
        ):
            decision, _ = svc.decision(action, company.id)
            assert decision == ActionDecision.BLOCK, f"{action} must stay blocked"

    def test_change_autonomy_requires_approval_even_at_high_autonomy(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision

        company = _company(db)
        AutonomyService(db).set_policy(company.id, autonomy_level="high_autonomy")
        decision, _ = AutonomyService(db).decision("change_autonomy", company.id)
        assert decision == ActionDecision.REQUIRE_APPROVAL

    def test_pending_gate_does_not_authorize(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.gates import ApprovalGateManager
        from app.startup.types import ApprovalRequiredError

        company = _company(db)
        gate = ApprovalGateManager(db).create(
            company_id=company.id,
            gate_type="budget_approval",
            requested_action={"action": "allocate_budget"},
            rationale="Not yet approved.",
        )
        try:
            AutonomyService(db).enforce(
                "allocate_budget",
                company.id,
                approved_gate_id=gate.id,
                estimated_cost=5000.0,
            )
            raise AssertionError("A pending gate must not authorize the action")
        except ApprovalRequiredError:
            pass


class TestPlanEndpointIsolation:
    """HTTP-level guard: ``/startup-plans`` is company-scoped end to end.

    A caller who knows a mission UUID must still present the owning company to
    list, read, or act on that mission's plans — otherwise the plan is a 404.
    """

    def test_foreign_company_cannot_list_or_read_plans(
        self, api_client: TestClient, db: Session
    ) -> None:
        from app.startup.mission import MissionManager
        from app.startup.plans import StartupPlanManager

        company_a = _company(db)
        company_b = _company(db)
        mission = MissionManager(db).create(
            company_id=company_a.id,
            title="Plan isolation mission",
            mission_statement="Classified plan.",
        )
        plan = StartupPlanManager(db).create(mission_id=mission.id)
        db.commit()

        base = "/api/v1/startup-plans"
        foreign = {"company_id": str(company_b.id), "mission_id": str(mission.id)}
        owner = {"company_id": str(company_a.id), "mission_id": str(mission.id)}

        # Company B cannot list plans for A's mission.
        resp = api_client.get(base, params=foreign)
        assert resp.status_code == 404
        # Company B cannot read A's plan.
        resp = api_client.get(f"{base}/{plan.id}", params=foreign)
        assert resp.status_code == 404

        # The owning company sees the list and the plan.
        resp = api_client.get(base, params=owner)
        assert resp.status_code == 200
        assert any(p["id"] == str(plan.id) for p in resp.json())
        resp = api_client.get(f"{base}/{plan.id}", params=owner)
        assert resp.status_code == 200
        assert resp.json()["mission_id"] == str(mission.id)
