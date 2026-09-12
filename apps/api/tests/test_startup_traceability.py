"""Tests for Phase 9 mission traceability — the mission graph.

Every startup artifact (mission → strategy → startup plan → goal → product →
project → task → execution → feedback) is linked into a directed graph as it is
created. ``trace`` answers "why does this task exist" by walking edges back to
the mission. These tests assert the edges the engine itself records and that a
trace from a task resolves to the mission.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Trace Co {_counter}", description="unit")


def _mission(db: Session, company):
    global _counter
    from app.startup.mission import MissionManager

    _counter += 1
    return MissionManager(db).create(
        company_id=company.id,
        title=f"Trace Mission {_counter}",
        mission_statement=(
            "Build an AI-powered developer productivity tool for small software "
            "teams with verifiable operating cycles."
        ),
        desired_outcome="Release a validated tool to an initial cohort.",
        target_market="small software teams",
        constraints=["Bounded autonomy only"],
        assumptions=["Teams adopt CLI tooling."],
        success_criteria=["Task success rate above 90%."],
    )


def _planned(db: Session):
    """Company + mission through analyze → validate → plan (records graph edges)."""
    from app.startup.mission import MissionManager

    company = _company(db)
    mission = _mission(db, company)
    mgr = MissionManager(db)
    mgr.analyze(mission)
    mgr.validate(mission)
    mgr.plan(mission)
    return company, mission


def _latest_plan(db: Session, mission_id: UUID):
    from sqlalchemy import select

    from app.db.models.startup import StartupPlan

    return db.scalar(
        select(StartupPlan)
        .where(StartupPlan.mission_id == mission_id)
        .order_by(StartupPlan.created_at.desc())
        .limit(1)
    )


def _approved_gate(db: Session, company_id):
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


def _bootstrapped(db: Session):
    """Full chain through approve + bootstrap → employees/products/projects."""
    from app.startup.bootstrap import CompanyBootstrapper
    from app.startup.plans import StartupPlanManager

    company, mission = _planned(db)
    plan = _latest_plan(db, mission.id)
    StartupPlanManager(db).approve(plan, actor="test")
    gate_id = _approved_gate(db, company.id)
    boot = CompanyBootstrapper(db).bootstrap(plan, approved_gate_id=gate_id, actor="test")
    return company, mission, plan, boot


def _agent_record(boot: dict) -> dict:
    """First provisioned employee record carrying a backing agent id."""
    for emp in boot["employees"]:
        if isinstance(emp, dict) and emp.get("agent_id"):
            return emp
    raise AssertionError("bootstrap must provision at least one agent")


def _queue_task(db: Session, agent_id: UUID, title: str):
    from app.db.models.task import TaskStatus
    from app.schemas.task import TaskCreate
    from app.services.task_service import TaskService

    task = TaskService(db).create(
        TaskCreate(
            title=title,
            description=f"Trace task: {title}",
            input_data={"focus": "trace"},
            assigned_agent_id=agent_id,
        )
    )
    task.status = TaskStatus.QUEUED
    db.commit()
    return task


class TestGraphEdges:
    def test_plan_pipeline_records_edges(self, db: Session) -> None:
        from app.startup.graph import MissionGraphBuilder

        company, mission = _planned(db)
        builder = MissionGraphBuilder(db)
        edges = builder.query(company.id)

        # strategic_plan → mission and startup_plan → strategic_plan.
        assert any(e.source_type == "strategic_plan" and e.target_type == "mission" for e in edges)
        assert any(
            e.source_type == "startup_plan" and e.target_type == "strategic_plan" for e in edges
        )

        # Every goal links derived_from the mission — no orphan goals.
        goal_edges = [e for e in edges if e.source_type == "goal"]
        assert goal_edges
        assert all(
            e.target_type == "mission" and e.relation.value == "derived_from" for e in goal_edges
        )

    def test_link_is_idempotent(self, db: Session) -> None:
        from app.db.models.startup import MissionGraphRelation
        from app.startup.graph import MissionGraphBuilder

        company, mission = _planned(db)
        builder = MissionGraphBuilder(db)
        first = builder.link(
            company_id=company.id,
            source_type="goal",
            source_id=UUID(int=11),
            target_type="mission",
            target_id=mission.id,
            relation=MissionGraphRelation.DERIVED_FROM,
        )
        second = builder.link(
            company_id=company.id,
            source_type="goal",
            source_id=UUID(int=11),
            target_type="mission",
            target_id=mission.id,
            relation=MissionGraphRelation.DERIVED_FROM,
        )
        assert first.id == second.id


class TestExecutionTrace:
    def test_execution_links_to_task(self, db: Session, phase6_settings) -> None:
        from app.startup.execution import ExecutionPlanner, Executor
        from app.startup.graph import MissionGraphBuilder

        company, mission, plan, boot = _bootstrapped(db)
        record = _agent_record(boot)
        task = _queue_task(db, UUID(record["agent_id"]), "Run a traceable build")

        exec_plan = ExecutionPlanner(db).create(
            company_id=company.id,
            mission_id=mission.id,
            objective_scope={"mission": str(mission.id), "projects": []},
            startup_plan_id=plan.id,
            task_ids=[task.id],
        )
        result = Executor(db).execute_plan(exec_plan)
        assert result["failures"] == []

        edges = MissionGraphBuilder(db).query(company.id)
        executed = [
            e
            for e in edges
            if e.source_type == "execution"
            and e.target_type == "task"
            and e.relation.value == "executed_by"
        ]
        assert executed, "Executor must record an execution → task edge"

    def test_trace_answers_why_task_exists(self, db: Session, phase6_settings) -> None:
        from app.db.models.startup import MissionGraphRelation
        from app.startup.execution import ExecutionPlanner, Executor
        from app.startup.graph import MissionGraphBuilder

        company, mission, plan, boot = _bootstrapped(db)
        record = _agent_record(boot)
        task = _queue_task(db, UUID(record["agent_id"]), "Why does this task exist")

        exec_plan = ExecutionPlanner(db).create(
            company_id=company.id,
            mission_id=mission.id,
            objective_scope={"mission": str(mission.id), "projects": []},
            startup_plan_id=plan.id,
            task_ids=[task.id],
        )
        Executor(db).execute_plan(exec_plan)

        builder = MissionGraphBuilder(db)
        # The company goal is already linked derived_from the mission by the
        # planner; attach this task to that goal so its lineage is complete.
        goal_edge = next(
            e
            for e in builder.query(company.id)
            if e.source_type == "goal" and e.target_type == "mission"
        )
        builder.link(
            company_id=company.id,
            source_type="task",
            source_id=task.id,
            target_type="goal",
            target_id=goal_edge.source_id,
            relation=MissionGraphRelation.DERIVED_FROM,
            metadata={"rationale": "Task contributes to a mission-derived goal"},
        )

        trace = builder.trace(company.id, "task", task.id)
        assert trace["origin"] == {"type": "task", "id": str(task.id)}
        assert trace["reached_mission"] is True
        # Lineage steps walk task → goal → mission (each edge child → parent).
        types = [step["to"]["type"] for step in trace["chain"]]
        assert "goal" in types
        assert "mission" in types


class TestGraphIsolation:
    def test_edges_are_company_scoped(self, db: Session) -> None:
        from app.startup.graph import MissionGraphBuilder

        company_a, _ = _planned(db)
        company_b = _company(db)
        builder = MissionGraphBuilder(db)
        edges_a = builder.query(company_a.id)
        assert edges_a
        assert builder.query(company_b.id) == []
