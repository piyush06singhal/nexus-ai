"""Tests for memory extraction from agent executions (Phase 4)."""

import asyncio
import json
from uuid import uuid4

from app.db.models.execution import AgentExecution, ExecutionStatus
from app.db.models.memory import MemoryOwnerType, MemorySourceType, MemoryType
from app.memory.extraction import extract_memories_from_execution


def _execution(*, status=ExecutionStatus.SUCCEEDED, output=None, error=None):
    exec_id = uuid4()
    agent_id = uuid4()
    execution = AgentExecution(
        id=exec_id,
        task_id=uuid4(),
        agent_id=agent_id,
        status=status,
        metadata_json=json.dumps({"task_title": "Quarterly analysis"}),
    )
    if output is not None:
        execution.output_data = json.dumps(output)
    if error is not None:
        execution.error = error
    execution.total_tokens = 1500
    execution.provider = "mock"
    execution.model_name = "mock-model"
    return execution, agent_id


def _extract(execution, agent_id, used_tools=None):
    return extract_memories_from_execution(
        execution,
        namespace="default",
        agent_id=agent_id,
        used_tools=used_tools,
    )


def asyncio_run(coro):
    return asyncio.run(coro)


def test_successful_execution_creates_episodic_memory():
    execution, agent_id = _execution(
        output={"summary": "Found 42 leads", "output": {"lead_count": 42}, "confidence": 0.9}
    )
    memories = asyncio_run(_extract(execution, agent_id))
    episodic = [m for m in memories if m.type == MemoryType.EPISODIC]
    assert episodic, "expected an episodic memory"
    m = episodic[0]
    assert "Quarterly analysis" in m.content
    assert m.owner_type == MemoryOwnerType.AGENT
    assert m.owner_id == agent_id
    assert m.source_type == MemorySourceType.EXECUTION
    assert m.source_id == execution.id
    assert m.status.value == "active"


def test_successful_execution_creates_semantic_memory():
    execution, agent_id = _execution(
        output={
            "summary": "Leads high",
            "output": {"lead_count": 42, "region": "APAC"},
            "confidence": 0.9,
        }
    )
    memories = asyncio_run(_extract(execution, agent_id))
    semantic = [m for m in memories if m.type == MemoryType.SEMANTIC]
    assert semantic
    assert "lead_count: 42" in semantic[0].content


def test_successful_execution_with_tools_creates_procedural():
    execution, agent_id = _execution(
        output={"summary": "Computed with tools", "output": {"result": 9}}
    )
    memories = asyncio_run(_extract(execution, agent_id, ["calculator", "datetime"]))
    procedural = [m for m in memories if m.type == MemoryType.PROCEDURAL]
    assert procedural
    assert "calculator" in procedural[0].content


def test_failed_execution_single_low_importance_episodic():
    execution, agent_id = _execution(status=ExecutionStatus.FAILED, error="model error")
    execution.total_tokens = 5
    memories = asyncio_run(_extract(execution, agent_id))
    # No output -> no semantic/procedural; just the episodic failure note.
    assert all(m.type == MemoryType.EPISODIC for m in memories)
    assert "Failed" in memories[0].content
    assert memories[0].importance < 0.7


def test_importance_rises_with_success_and_output():
    _, agent_id = _execution(output={"summary": "x", "output": {"k": 1}})
    execution = _execution(output={"summary": "x", "output": {"k": 1}})[0]
    memories = asyncio_run(_extract(execution, agent_id))
    episodic = next(m for m in memories if m.type == MemoryType.EPISODIC)
    assert episodic.importance >= 0.75


def test_embeddings_attached_when_provider_given():
    from app.memory.embedding import MockEmbeddingProvider

    execution, agent_id = _execution(output={"summary": "s", "output": {"k": 1}})
    memories = asyncio_run(
        extract_memories_from_execution(
            execution,
            namespace="default",
            agent_id=agent_id,
            embedding_provider=MockEmbeddingProvider(),
        )
    )
    assert memories
    assert all(m.embedding for m in memories)
