"""Tests for Phase 9 bounded autonomy, approval gates, and replanning.

Governance-first: allowed/blocked/approval-required actions, never-autonomous
actions (finance/legal/hiring), policy + budget caps, and the replanning
engine's trigger → bounded response selection.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Autonomy Co {_counter}", description="unit")


def _budgeted_company(db: Session, *, limit: float = 1000.0):
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


def _approved_gate(db: Session, company_id, gate_type: str, action: str):
    from app.startup.gates import ApprovalGateManager

    manager = ApprovalGateManager(db)
    gate = manager.create(
        company_id=company_id,
        gate_type=gate_type,
        requested_action={"action": action},
        rationale="Unit test gate",
        risk_level="low",
    )
    manager.approve(company_id, gate.id, approver_id=None)
    return gate.id


class TestAutonomyGovernance:
    def test_default_level_is_bounded(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        policy = AutonomyService(db).get_policy(company.id)
        assert policy.autonomy_level.value == "bounded_autonomy"

    def test_execute_task_auto_allowed(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision

        company = _company(db)
        decision, reason = AutonomyService(db).decision("execute_task", company.id)
        assert decision == ActionDecision.ALLOW
        assert "auto-allowed" in reason

    def test_never_autonomous_actions_blocked(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision

        company = _company(db)
        svc = AutonomyService(db)
        for action in (
            "finance",
            "legal",
            "hire_human",
            "fire_employee",
            "self_modify",
            "external_publish",
            "browser_automation",
        ):
            decision, _ = svc.decision(action, company.id)
            assert decision == ActionDecision.BLOCK, f"{action} must be blocked"

    def test_change_autonomy_requires_approval(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision

        company = _company(db)
        decision, _ = AutonomyService(db).decision("change_autonomy", company.id)
        assert decision == ActionDecision.REQUIRE_APPROVAL

    def test_provision_employee_requires_approval(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision

        company = _company(db)
        decision, _ = AutonomyService(db).decision("provision_employee", company.id)
        assert decision == ActionDecision.REQUIRE_APPROVAL

    def test_enforce_raises_without_gate(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        try:
            AutonomyService(db).enforce("provision_employee", company.id)
            raise AssertionError("Must raise without an approved gate")
        except Exception as exc:
            assert "requires approval" in str(exc)

    def test_enforce_passes_with_approved_gate(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision

        company = _company(db)
        gate_id = _approved_gate(db, company.id, "workforce_approval", "provision_employee")
        decision = AutonomyService(db).enforce(
            "provision_employee", company.id, approved_gate_id=gate_id
        )
        assert decision == ActionDecision.ALLOW

    def test_budget_cap_triggers_approval(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision

        company = _budgeted_company(db, limit=1000.0)
        # An allowed action over the company budget must require approval.
        decision, _ = AutonomyService(db).decision(
            "allocate_budget", company.id, estimated_cost=5000.0
        )
        assert decision == ActionDecision.REQUIRE_APPROVAL

    def test_manual_level_blocks_auto(self, db: Session) -> None:
        from app.startup.autonomy import AutonomyService
        from app.startup.types import ActionDecision

        company = _company(db)
        svc = AutonomyService(db)
        svc.set_policy(company.id, autonomy_level="manual")
        decision, _ = svc.decision("execute_task", company.id)
        assert decision == ActionDecision.REQUIRE_APPROVAL


class TestApprovalGates:
    def test_gate_lifecycle(self, db: Session) -> None:
        from app.startup.gates import ApprovalGateManager

        company = _company(db)
        mgr = ApprovalGateManager(db)
        gate = mgr.create(
            company_id=company.id,
            gate_type="budget_approval",
            requested_action={"action": "allocate_budget"},
            rationale="Increase budget",
            risk_level="medium",
        )
        assert gate.status.value == "pending"
        assert gate.id in [g.id for g in mgr.pending(company.id)]

        mgr.approve(company.id, gate.id, approver_id=None)
        assert mgr.get(company.id, gate.id).status.value == "approved"

        # A separate pending gate can be rejected.
        other = mgr.create(
            company_id=company.id,
            gate_type="high_risk_action_approval",
            requested_action={"action": "replan"},
            rationale="Replan that is declined",
            risk_level="high",
        )
        mgr.reject(company.id, other.id, approver_id=None)
        assert mgr.get(company.id, other.id).status.value == "rejected"

    def test_cross_company_gate_isolation(self, db: Session) -> None:
        from app.startup.gates import ApprovalGateManager

        company_a = _company(db)
        company_b = _company(db)
        mgr = ApprovalGateManager(db)
        gate = mgr.create(
            company_id=company_a.id,
            gate_type="high_risk_action_approval",
            requested_action={"action": "replan"},
            rationale="Replan",
            risk_level="high",
        )
        assert mgr.get(company_b.id, gate.id) is None


class TestReplanning:
    def _company_with_state(self, db: Session, *, verification: float = 1.0):
        """Seed a company + a fake StateSnapshot-like state object."""
        company = _company(db)

        class _State:
            metrics = {"kpis": [], "budget": {"utilization": 0.1}, "open_risks": 0}
            dimensions = {"verification": verification}

        return company, _State()

    def test_continue_when_no_trigger(self, db: Session) -> None:
        from app.startup.replan import ReplanningEngine
        from app.startup.types import ReplanResponse

        company, state = self._company_with_state(db)
        decision = ReplanningEngine(db).evaluate(company_id=company.id, state=state)
        assert decision.response == ReplanResponse.CONTINUE

    def test_kpi_underperformance_reprioritizes(self, db: Session) -> None:
        from app.startup.projects import ProjectManager
        from app.startup.replan import ReplanningEngine
        from app.startup.types import ReplanResponse

        company = _company(db)
        ProjectManager(db).create(
            company_id=company.id,
            name="Low value",
            priority=0,
            status="active",
        )

        class _State:
            metrics = {
                "kpis": [{"attainment": 0.3}],
                "budget": {"utilization": 0.1},
                "open_risks": 0,
            }
            dimensions = {"verification": 1.0}

        decision = ReplanningEngine(db).evaluate(company_id=company.id, state=_State())
        assert decision.response == ReplanResponse.REPRIORITIZE

    def test_verification_failure_replans(self, db: Session) -> None:
        from app.startup.replan import ReplanningEngine
        from app.startup.types import ReplanResponse

        company, state = self._company_with_state(db, verification=0.3)
        decision = ReplanningEngine(db).evaluate(company_id=company.id, state=state)
        assert decision.response == ReplanResponse.REPLAN

    def test_execution_failure_reassigns(self, db: Session) -> None:
        from app.startup.replan import ReplanningEngine
        from app.startup.types import ReplanResponse

        company = _company(db)
        decision = ReplanningEngine(db).evaluate(
            company_id=company.id,
            execution_outcome={"failures": [{"task_id": "t"}]},
        )
        assert decision.response == ReplanResponse.REASSIGN

    def test_budget_threshold_requests_approval(self, db: Session) -> None:
        from app.startup.replan import ReplanningEngine
        from app.startup.types import ReplanResponse

        company = _company(db)

        class _State:
            metrics = {
                "kpis": [],
                "budget": {"utilization": 0.95},
                "open_risks": 0,
            }
            dimensions = {"verification": 1.0}

        decision = ReplanningEngine(db).evaluate(company_id=company.id, state=_State())
        assert decision.response == ReplanResponse.REQUEST_APPROVAL
        assert decision.requires_approval is True

    def test_replan_attempt_cap_escalates(self, db: Session) -> None:
        from app.startup.replan import ReplanningEngine
        from app.startup.types import ReplanResponse

        company = _company(db)
        engine = ReplanningEngine(db)
        decision = engine.evaluate(
            company_id=company.id,
            checked=settings_startup_max(ReplanningEngine),
        )
        assert decision.response == ReplanResponse.ESCALATE
        assert decision.requires_approval is True

    def test_apply_repriotitize_under_gate(self, db: Session) -> None:
        from app.startup.projects import ProjectManager
        from app.startup.replan import ReplanningEngine
        from app.startup.types import ReplanDecision, ReplanResponse

        company = _company(db)
        project = ProjectManager(db).create(
            company_id=company.id,
            name="P",
            priority=3,
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
        gate_id = _approved_gate(db, company.id, "high_risk_action_approval", "replan")
        result = ReplanningEngine(db).apply(
            company_id=company.id, decision=decision, approved_gate_id=gate_id
        )
        assert result["applied"] == [{"action": "reprioritize_project", "ok": True}]
        assert ProjectManager(db).get(company.id, project.id).priority == 0


def settings_startup_max(ReplanningEngine):
    from app.core.config import settings

    return settings.startup_max_replanning_attempts
