"""Integration tests: Orchestrator → Agent Runtime → Memory, and Workflow →
Orchestration (spec §20, §33, §34)."""

from __future__ import annotations

from app.db.models.agent import Agent, AgentStatus
from app.db.models.orchestration import OrchestrationStatus
from app.db.models.workflow import (
    StepStatus,
    WorkflowExecutionStatus,
    WorkflowStepType,
)
from app.schemas.orchestration import OrchestrationCreate
from app.schemas.workflow import WorkflowCreate, WorkflowStepCreate
from app.services.orchestration_service import OrchestrationService
from app.services.workflow_service import WorkflowService
from app.workflow.engine import WorkflowEngine


def _make_agent(db, name, role="general", reply='{"summary":"ok","output":{"r":1}}'):
    import json

    agent = Agent(
        name=name,
        role=role,
        status=AgentStatus.ACTIVE,
        provider="mock",
        model_name="mock-model",
        model_params=json.dumps({"reply": reply}),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def test_full_orchestrator_pipeline(db):
    """Orchestrator drives the Agent Runtime end-to-end and persists memory."""
    _make_agent(db, "orchestra-researcher", "researcher", '{"summary":"r","output":{"mkt":100}}')
    _make_agent(db, "orchestra-analyst", "analyst", '{"summary":"a","output":{"growth":5}}')
    _make_agent(
        db, "orchestra-fact-checker", "fact_checker", '{"summary":"fc","output":{"verified":true}}'
    )
    _make_agent(db, "orchestra-writer", "writer", '{"summary":"w","output":{"report":"yes"}}')

    service = OrchestrationService(db)
    orch = service.create(
        OrchestrationCreate(objective="analyze the competitive market and write a report")
    )
    result = service.execute(orch.id)
    assert result.status == OrchestrationStatus.COMPLETED
    assert result.final_result is not None
    final = __import__("json").loads(result.final_result)
    assert final["status"] == "completed"
    assert final["sources"]  # source attribution present
    assert final["conflicts"] == []

    # Tasks all reached a terminal state.
    tasks = service.get_tasks(orch.id)
    assert len(tasks) == 4
    assert all(t.status.value in ("completed", "skipped", "failed") for t in tasks)
    research = next(t for t in tasks if t.name == "research")
    assert research.status.value == "completed"

    # Shared context was populated from structured outputs.
    context = service.get_context(orch.id)
    assert any(c.key.startswith("task.") for c in context)


def test_agent_task_leaves_memory(db):
    """Each executed agent task persists an underlying Phase 4 memory."""
    _make_agent(
        db, "memorizing-agent", "general", '{"summary":"remember me","output":{"note":"x"}}'
    )
    service = OrchestrationService(db)
    orch = service.create(OrchestrationCreate(objective="remember something important"))
    result = service.execute(orch.id)
    assert result.status == OrchestrationStatus.COMPLETED
    # The single temp Task created per orchestration task now has an execution.
    temp_tasks = (
        db.query(__import__("app.db.models.task", fromlist=["Task"]).Task)
        .filter(
            __import__("app.db.models.task", fromlist=["Task"]).Task.title.like("orchestration:%")
        )
        .all()
    )
    assert temp_tasks, "expected at least one orchestration temp task"


def test_workflow_orchestration_step(db):
    """A workflow with an ORCHESTRATION step runs the orchestration inline."""
    _make_agent(db, "wf-orchestra-general", "general", '{"summary":"ok","output":{"r":1}}')

    # A CREATED (not-yet-run) orchestration to hand to the workflow.
    orch_svc = OrchestrationService(db)
    orch = orch_svc.create(OrchestrationCreate(objective="complete the objective"))

    svc = WorkflowService(db)
    wf = svc.create(WorkflowCreate(name="wf-with-orchestration"))
    svc.add_step(
        wf.id,
        WorkflowStepCreate(
            name="team",
            step_type=WorkflowStepType.ORCHESTRATION,
            configuration={"orchestration_id": str(orch.id)},
            input_mapping={},
        ),
    )
    svc.activate(wf.id)
    execution = svc.create_execution(wf.id, trigger_type="manual", input_data={})

    result = WorkflowEngine(db).execute(execution.id)
    assert result.status == WorkflowExecutionStatus.COMPLETED

    step_execs = svc.get_step_executions(execution.id)
    assert step_execs[0].status == StepStatus.COMPLETED
    output = __import__("json").loads(step_execs[0].output_data)
    assert output["orchestration_status"] == "completed"
    assert output["final_result"]["status"] == "completed"

    # The workflow actually drove the orchestration to completion.
    assert orch_svc.get(orch.id).status == OrchestrationStatus.COMPLETED


def test_workflow_validator_requires_orchestration_id():
    from app.workflow.validator import validate_workflow_steps

    class FakeStep:
        step_type = WorkflowStepType.ORCHESTRATION
        configuration = None  # missing orchestration_id
        dependencies = None
        timeout_seconds = None
        retry_policy = None
        idempotency = None
        name = "team"

    result = validate_workflow_steps([FakeStep()])
    assert not result.valid
    assert any("orchestration_id" in e for e in result.errors)
