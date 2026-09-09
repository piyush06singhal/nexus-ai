"""Tests for the AgentRuntime orchestrator.

Exercises the pipeline (validate → build context → execute model → parse →
persist) against an in-memory SQLite DB with an injected MockProvider.
"""

from uuid import uuid4

import pytest

from app.ai.providers.mock_provider import MockProvider
from app.ai.types import TokenUsage
from app.core.errors import ServiceUnavailableError, ValidationError
from app.db.models.agent import AgentStatus
from app.db.models.execution import ExecutionStatus
from app.runtime.runtime import AgentRuntime
from app.schemas.agent import AgentCreate
from app.schemas.task import TaskCreate
from app.services.agent_service import AgentService
from app.services.execution_service import ExecutionService
from app.services.task_service import TaskService

GOOD_JSON = (
    '{"summary": "Analysis complete", "output": {"status": "done"}, '
    '"confidence": 0.9, "followup_actions": ["review"]}'
)


def _build_runtime(db, provider):
    return AgentRuntime(
        agent_service=AgentService(db),
        task_service=TaskService(db),
        execution_service=ExecutionService(db),
        provider=provider,
    )


def _seed_active_agent_and_task(db, *, agent_status=AgentStatus.ACTIVE, provider_name="mock"):
    agent = AgentService(db).create(
        AgentCreate(
            name=f"agent-{uuid4().hex[:8]}",
            status=agent_status,
            provider=provider_name,
            model_name="mock-model",
        )
    )
    task = TaskService(db).create(TaskCreate(title="Do the thing", input_data={"n": 1}))
    TaskService(db).assign(task.id, agent.id)
    return agent, task


def test_runtime_executes_and_persists_success(db):
    agent, task = _seed_active_agent_and_task(db)
    provider = MockProvider(
        reply=GOOD_JSON, usage=TokenUsage(prompt_tokens=30, completion_tokens=10, total_tokens=40)
    )
    runtime = _build_runtime(db, provider)

    execution = runtime.execute_task(task.id)

    assert execution.status == ExecutionStatus.SUCCEEDED
    assert execution.agent_id == agent.id
    assert execution.task_id == task.id
    assert execution.provider == "mock"
    assert execution.total_tokens == 40
    assert execution.output_data is not None
    assert "Analysis complete" in execution.output_data
    # Task should now be completed.
    assert TaskService(db).get(task.id).status.value == "completed"


def test_runtime_resolves_provider_from_agent_branch_not_relevant_here(db):
    """Provider injection covers resolution; here just assert provider recorded."""
    agent, task = _seed_active_agent_and_task(db)
    runtime = _build_runtime(db, MockProvider(reply=GOOD_JSON))
    execution = runtime.execute_task(task.id)
    assert execution.model_name == "mock-model"


def test_runtime_fails_on_unassigned_task(db):
    from app.schemas.task import TaskCreate as TC

    task = TaskService(db).create(TC(title="Unassigned"))
    runtime = _build_runtime(db, MockProvider(reply=GOOD_JSON))
    with pytest.raises(ValidationError):
        runtime.execute_task(task.id)


def test_runtime_fails_on_non_active_agent(db):
    agent, task = _seed_active_agent_and_task(db, agent_status=AgentStatus.DRAFT)
    runtime = _build_runtime(db, MockProvider(reply=GOOD_JSON))
    with pytest.raises(ValidationError):
        runtime.execute_task(task.id)


def test_runtime_fails_and_persists_error_on_bad_output(db):
    agent, task = _seed_active_agent_and_task(db)
    # Malformed JSON -> runtime should fail and record the error + failed task.
    provider = MockProvider(reply="this is not json at all")
    runtime = _build_runtime(db, provider)

    with pytest.raises(ServiceUnavailableError):
        runtime.execute_task(task.id)

    executions = ExecutionService(db).list_by_task(task.id)
    assert len(executions) == 1
    assert executions[0].status == ExecutionStatus.FAILED
    assert executions[0].error is not None
    assert TaskService(db).get(task.id).status.value == "failed"


def test_runtime_get_execution(db):
    agent, task = _seed_active_agent_and_task(db)
    runtime = _build_runtime(db, MockProvider(reply=GOOD_JSON))
    execution = runtime.execute_task(task.id)
    fetched = runtime.get_execution(execution.id)
    assert fetched.id == execution.id
