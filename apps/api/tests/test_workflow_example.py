"""End-to-end "Daily Research Workflow" (spec §39).

A realistic workflow with three steps wired together:
    A: AGENT_TASK  — a researcher gathers data (mock provider).
    B: CONDITION   — branch on whether the research found enough leads.
    C: TOOL_ACTION — send a notification if the condition passes.

Drives the whole stack: service → engine → runtime → tool executor → DB.
"""

import pytest

from app.core.config import settings
from app.db.models.agent import AgentStatus
from app.db.models.workflow import StepStatus, WorkflowExecutionStatus
from app.schemas.agent import AgentCreate
from app.schemas.workflow import WorkflowCreate, WorkflowStepCreate, WorkflowStepType
from app.services.agent_service import AgentService
from app.services.workflow_service import WorkflowService
from app.workflow.engine import WorkflowEngine


@pytest.fixture(autouse=True)
def _sync_execute(monkeypatch):
    monkeypatch.setattr(settings, "workflow_execute_sync", True)


def _make_agent(db, name):
    return AgentService(db).create(
        AgentCreate(
            name=name,
            role="researcher",
            status=AgentStatus.ACTIVE,
            provider="mock",
            model_name="mock-model",
        )
    )


@pytest.fixture
def daily_research_wf(db):
    """Build and activate the Daily Research Workflow."""
    svc = WorkflowService(db)
    researcher = _make_agent(db, "researcher")

    wf = svc.create(
        WorkflowCreate(
            name="Daily Research Workflow",
            description="Gathers research and notifies when promising.",
        )
    )
    # A: gather data.
    svc.add_step(
        wf.id,
        WorkflowStepCreate(
            name="gather",
            step_type=WorkflowStepType.AGENT_TASK,
            order=1,
            configuration={"agent_id": str(researcher.id), "input_mapping": {}},
        ),
    )
    # B: condition on input confidence.
    svc.add_step(
        wf.id,
        WorkflowStepCreate(
            name="promising",
            step_type=WorkflowStepType.CONDITION,
            order=2,
            dependencies=["gather"],
            configuration={
                "condition": {"field": "input.confidence_score", "op": "gte", "value": 0.5}
            },
        ),
    )
    # C: notify if the condition passes.
    svc.add_step(
        wf.id,
        WorkflowStepCreate(
            name="notify",
            step_type=WorkflowStepType.TOOL_ACTION,
            order=3,
            dependencies=["promising"],
            configuration={
                "tool_name": "calculator",
                "arguments": {"expression": "1 + 1"},
                "agent_id": str(researcher.id),
            },
        ),
    )
    svc.activate(wf.id)
    return svc, wf, researcher


class TestDailyResearchWorkflow:
    def test_workflow_completes_when_condition_met(self, db, daily_research_wf):
        svc, wf, _ = daily_research_wf
        execution = svc.create_execution(
            wf.id, trigger_type="manual", input_data={"confidence_score": 0.9}
        )

        result = WorkflowEngine(db).execute(execution.id)

        assert result.status == WorkflowExecutionStatus.COMPLETED
        step_execs = svc.get_step_executions(execution.id)
        assert len(step_execs) == 3
        # gather ran, condition passed, notify ran.
        assert all(s.status == StepStatus.COMPLETED for s in step_execs)

    def test_downstream_skipped_when_condition_not_met(self, db, daily_research_wf):
        svc, wf, _ = daily_research_wf
        execution = svc.create_execution(
            wf.id, trigger_type="manual", input_data={"confidence_score": 0.1}
        )

        result = WorkflowEngine(db).execute(execution.id)

        assert result.status == WorkflowExecutionStatus.COMPLETED
        step_execs = svc.get_step_executions(execution.id)
        statuses = {s.status for s in step_execs}
        # gather + promising completed; notify skipped.
        assert StepStatus.COMPLETED in statuses
        assert StepStatus.SKIPPED in statuses

    def test_agent_execution_persisted(self, db, daily_research_wf):
        svc, wf, researcher = daily_research_wf
        execution = svc.create_execution(
            wf.id, trigger_type="manual", input_data={"confidence_score": 0.9}
        )
        WorkflowEngine(db).execute(execution.id)

        # The agent task created a temp Task + AgentExecution.
        from sqlalchemy import select

        from app.db.models.execution import AgentExecution

        agent_execs = list(
            db.scalars(select(AgentExecution).where(AgentExecution.agent_id == researcher.id))
        )
        assert len(agent_execs) >= 1
        assert agent_execs[0].status.value == "succeeded"
