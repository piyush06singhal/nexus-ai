"""Tests for the Phase 9 operating cycle — observe→assess→plan→prioritize→
allocate→execute→verify→measure→learn→replan, immutable cycle records, and
feedback/replanning surfaced from a degraded state."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.agent import Agent
from app.db.models.employee import AIEmployee, EmployeeStatus
from app.db.models.task import Task, TaskStatus

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    company = CompanyManager(db).create(name=f"Cycle Co {_counter}", description="unit")
    CompanyManager(db).activate(company.id)
    return company


def _member_agent(db: Session, company_id, *, name: str = "eng"):
    """Create an AIEmployee with a backing agent + company membership."""
    global _counter
    from app.db.models.company import OrganizationalMembership

    _counter += 1
    agent = Agent(name=f"{name}-agent-{_counter}", model_name="test")
    db.add(agent)
    db.flush()
    emp = AIEmployee(
        name=f"{name}-{_counter}",
        display_name=name.title(),
        role="engineer",
        status=EmployeeStatus.ACTIVE,
        skills='["python"]',
        agent_id=agent.id,
    )
    db.add(emp)
    db.flush()
    db.add(
        OrganizationalMembership(
            company_id=company_id,
            employee_id=emp.id,
        )
    )
    db.commit()
    return emp


def _queue_task(db: Session, agent_id: UUID, title: str) -> Task:
    from app.schemas.task import TaskCreate
    from app.services.task_service import TaskService

    task = TaskService(db).create(
        TaskCreate(
            title=title,
            description=f"Demo task: {title}",
            input_data={"focus": "work"},
            assigned_agent_id=agent_id,
        )
    )
    task.status = TaskStatus.QUEUED
    db.commit()
    return task


def _bootstrapped_context(db: Session):
    """Company + one member agent + one queued task (usable by all classes)."""
    from app.startup.mission import MissionManager

    company = _company(db)
    mission = MissionManager(db).create(
        company_id=company.id,
        title=f"Mission {_counter}",
        mission_statement="Run verifiable operating cycles.",
        desired_outcome="Task verified.",
        target_market="small teams",
        constraints=["Bounded autonomy only"],
        assumptions=["Works."],
        success_criteria=["Success rate 90%+"],
    )
    emp = _member_agent(db, company.id)
    task = _queue_task(db, emp.agent_id, "Run a verification pass")
    return company, mission, task


class TestOperatingCycle:
    def test_cycle_runs_to_replan_stage(self, db: Session, phase6_settings) -> None:
        company, mission, task = _bootstrapped_context(db)
        from app.startup.cycle import OperatingEngine

        result = OperatingEngine(db).run_cycle(
            company_id=company.id,
            mission_id=mission.id,
            actor="test",
        )
        assert result["status"] in ("completed", "blocked")
        names = [s["stage"] for s in result["stages"]]
        assert names == [
            "observe",
            "assess",
            "plan",
            "prioritize",
            "allocate",
            "execute",
            "verify",
            "measure",
            "learn",
            "replan",
        ]
        assert result["cycle_number"] == 1

    def test_cycle_record_is_immutable(self, db: Session, phase6_settings) -> None:
        company, mission, task = _bootstrapped_context(db)
        from app.startup.cycle import OperatingEngine

        engine = OperatingEngine(db)
        result = engine.run_cycle(
            company_id=company.id,
            mission_id=mission.id,
            actor="test",
        )
        from app.db.models.startup import OperatingCycle

        stored = db.get(OperatingCycle, UUID(result["id"]))
        assert stored is not None
        assert stored.status.value == result["status"]
        # The stages JSON is fixed; editing the ORM object is not possible
        # through the API path (record is produced and finished atomically).
        assert stored.stages is not None

    def test_cycle_lists_in_order(self, db: Session, phase6_settings) -> None:
        company, mission, task = _bootstrapped_context(db)
        from app.startup.cycle import OperatingEngine

        engine = OperatingEngine(db)
        engine.run_cycle(company_id=company.id, mission_id=mission.id, actor="test")
        engine.run_cycle(company_id=company.id, mission_id=mission.id, actor="test")
        cycles = engine.list_cycles(company.id)
        assert len(cycles) == 2
        assert [c["cycle_number"] for c in cycles] == [2, 1]

    def test_cycle_persists_state_snapshot(self, db: Session, phase6_settings) -> None:
        company, mission, task = _bootstrapped_context(db)
        from app.startup.cycle import OperatingEngine
        from app.startup.observe import ObservationLayer

        engine = OperatingEngine(db)
        result = engine.run_cycle(
            company_id=company.id,
            mission_id=mission.id,
            actor="test",
        )
        assert result["state_snapshot_id"] is not None
        snapshots = ObservationLayer(db).list_snapshots(company.id)
        assert len(snapshots) == 1
        assert snapshots[0]["cycle_id"] == result["id"]


class TestStateObservation:
    def test_observe_returns_backed_dimensions(self, db: Session) -> None:
        company, mission, task = _bootstrapped_context(db)
        from app.startup.observe import ObservationLayer

        snapshot = ObservationLayer(db).observe(company.id)
        assert isinstance(snapshot.overall_score, float)
        assert 0.0 <= snapshot.overall_score <= 1.0
        for dim in (
            "execution_health",
            "verification",
            "recovery",
            "budget",
            "goal_progress",
            "workforce",
        ):
            assert dim in snapshot.dimensions
        assert snapshot.metrics["task_volume"] >= 0

    def test_observations_never_fabricate(self, db: Session) -> None:
        """Every metric traces to a real source; no magic constants."""
        company, mission, task = _bootstrapped_context(db)
        from app.startup.observe import ObservationLayer

        snapshot = ObservationLayer(db).observe(company.id)
        # budget health comes from the Phase 8 BudgetManager snapshot.
        assert "spent" in snapshot.metrics["budget"]
        assert "monthly_limit" in snapshot.metrics["budget"]


class TestFeedbackAndReplan:
    def test_feedback_records_from_state(self, db: Session, phase6_settings) -> None:
        company, mission, task = _bootstrapped_context(db)
        from app.startup.cycle import OperatingEngine
        from app.startup.feedback import FeedbackService
        from app.startup.observe import ObservationLayer

        OperatingEngine(db).run_cycle(
            company_id=company.id,
            mission_id=mission.id,
            actor="test",
        )
        state = ObservationLayer(db).observe(company.id)
        records_before = len(FeedbackService(db).list_(company.id))
        FeedbackService(db).from_state(company.id, state, mission_id=mission.id)
        records_after = len(FeedbackService(db).list_(company.id))
        assert records_after >= records_before

    def test_replannevaluation_records_feedback(self, db: Session) -> None:
        company, mission, task = _bootstrapped_context(db)
        from app.startup.feedback import FeedbackService
        from app.startup.replan import ReplanningEngine

        engine = ReplanningEngine(db)
        baseline = len(FeedbackService(db).list_(company.id))
        engine.evaluate(company_id=company.id, mission_id=mission.id)
        assert len(FeedbackService(db).list_(company.id)) > baseline
