"""End-to-end tests: runtime auto-extraction + retrieval integration (Phase 4)."""

from uuid import uuid4

import pytest

from app.ai.providers.mock_provider import MockProvider
from app.db.models.agent import AgentStatus
from app.db.models.memory import Memory, MemorySourceType, MemoryType
from app.runtime.context import build_context
from app.runtime.runtime import AgentRuntime
from app.schemas.agent import AgentCreate
from app.schemas.task import TaskCreate
from app.services.agent_service import AgentService
from app.services.execution_service import ExecutionService
from app.services.memory_service import MemoryService
from app.services.task_service import TaskService

GOOD_JSON = (
    '{"summary": "Revenue analysis complete", "output": {"revenue": 42, "region": "APAC"}, '
    '"confidence": 0.9, "followup_actions": []}'
)


def _build_runtime(db):
    return AgentRuntime(
        agent_service=AgentService(db),
        task_service=TaskService(db),
        execution_service=ExecutionService(db),
        provider=MockProvider(reply=GOOD_JSON),
    )


def _seed_agent(db, name=None):
    agent = AgentService(db).create(
        AgentCreate(
            name=name or f"agent-{uuid4().hex[:8]}",
            status=AgentStatus.ACTIVE,
            provider="mock",
            model_name="mock-model",
        )
    )
    return agent


def _run_task(db, runtime, agent_id, *, title, description=None, input_data=None):
    task = TaskService(db).create(
        TaskCreate(title=title, description=description, input_data=input_data)
    )
    TaskService(db).assign(task.id, agent_id)
    return runtime.execute_task(task.id)


def test_execution_auto_extracts_memories(db):
    agent = _seed_agent(db)
    runtime = _build_runtime(db)
    execution = _run_task(
        db, runtime, agent.id, title="Analyze revenue trends", input_data={"q": 1}
    )
    assert execution.status.value == "succeeded"

    memories = db.query(Memory).filter(Memory.source_id == execution.id).all()
    assert memories, "execution should have auto-extracted memories"
    types = {m.type for m in memories}
    assert MemoryType.EPISODIC in types
    assert MemoryType.SEMANTIC in types
    # Provenance is recorded.
    assert all(m.source_type == MemorySourceType.EXECUTION for m in memories)
    assert all(m.owner_id == agent.id for m in memories)


def test_second_execution_recalls_memory_and_tracks_access(db):
    agent = _seed_agent(db)
    runtime = _build_runtime(db)
    # First run stores a semantic memory about revenue.
    first = _run_task(db, runtime, agent.id, title="Analyze revenue trends", input_data={"q": 1})
    memory = (
        db.query(Memory)
        .filter(Memory.source_id == first.id, Memory.type == MemoryType.SEMANTIC)
        .first()
    )
    assert memory is not None
    assert memory.access_count == 0

    # Second, related run should retrieve that memory (access tracked).
    _run_task(db, runtime, agent.id, title="Revenue growth follow-up", input_data={"q": 2})
    db.refresh(memory)
    assert memory.access_count > 0


def test_build_context_injects_memories(db):
    agent = _seed_agent(db)
    runtime = _build_runtime(db)
    first = _run_task(db, runtime, agent.id, title="Analyze revenue trends", input_data={"q": 1})
    memory = (
        db.query(Memory)
        .filter(Memory.source_id == first.id, Memory.type == MemoryType.SEMANTIC)
        .first()
    )
    task = TaskService(db).create(TaskCreate(title="Revenue follow-up", input_data={"q": 2}))
    TaskService(db).assign(task.id, agent.id)

    agentsvc = AgentService(db)
    runtime_agent = agentsvc.get(agent.id)
    messages = build_context(
        runtime_agent,
        task,
        memories=[{"content": memory.content, "type": "semantic", "importance": 0.7}],
    )
    system_prompt = messages[0].content
    assert "## Relevant Memories" in system_prompt
    assert "revenue" in system_prompt.lower()


def test_working_memory_ttl_expires(db):
    from datetime import UTC, datetime, timedelta

    svc = MemoryService(db)
    from app.schemas.memory import MemoryCreate

    svc.create(
        MemoryCreate(
            namespace="default",
            type=MemoryType.WORKING,
            content="ephemeral context",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
            owner_id=uuid4(),
        )
    )
    expired = svc.cleanup_expired()
    assert expired == 1


def test_failed_execution_extracts_only_episodic(db):
    from app.core.errors import ServiceUnavailableError

    agent = _seed_agent(db)
    bad_runtime = AgentRuntime(
        agent_service=AgentService(db),
        task_service=TaskService(db),
        execution_service=ExecutionService(db),
        provider=MockProvider(reply="this is not json"),
    )
    with pytest.raises(ServiceUnavailableError):
        _run_task(db, bad_runtime, agent.id, title="Will fail", input_data={})
    # A failed run leaves no semantic memory for the agent.
    leaked = (
        db.query(Memory)
        .filter(Memory.type == MemoryType.SEMANTIC, Memory.owner_id == agent.id)
        .all()
    )
    assert leaked == []
