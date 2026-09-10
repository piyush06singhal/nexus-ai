"""Tests for capability-based agent selection (spec §4, §33)."""

from __future__ import annotations

import uuid

import pytest

from app.db.models.agent import Agent, AgentStatus
from app.orchestration.selector import CapabilityAgentSelector
from app.orchestration.types import NoAgentAvailableError, PlanTask


def _agent(name, role, status=AgentStatus.ACTIVE, provider="mock", model_name="m"):
    return Agent(
        id=uuid.uuid4(),
        name=name,
        role=role,
        status=status,
        provider=provider,
        model_name=model_name,
    )


def test_matches_agent_by_required_capability(db):
    researcher = _agent("r1", "researcher")
    db.add(researcher)
    db.commit()
    selector = CapabilityAgentSelector()
    sel = selector.select(
        PlanTask(name="research", required_capabilities=["research"]),
        [researcher],
        db,
    )
    assert sel.agent_id == researcher.id
    assert "research" in sel.matched_capabilities


def test_prefers_specialist_agent(db):
    general = _agent("general", "general")
    researcher = _agent("specialist", "researcher")
    db.add_all([general, researcher])
    db.commit()
    selector = CapabilityAgentSelector()
    sel = selector.select(
        PlanTask(name="research", required_capabilities=["research"]),
        [general, researcher],
        db,
    )
    assert sel.agent_id == researcher.id


def test_skips_inactive_agent(db):
    inactive = _agent("sleep", "researcher", status=AgentStatus.DRAFT)
    db.add(inactive)
    db.commit()
    selector = CapabilityAgentSelector()
    with pytest.raises(NoAgentAvailableError):
        selector.select(
            PlanTask(name="research", required_capabilities=["research"]),
            [inactive],
            db,
        )


def test_raises_when_no_agent_matches(db):
    writer = _agent("w", "writer")
    db.add(writer)
    db.commit()
    selector = CapabilityAgentSelector()
    with pytest.raises(NoAgentAvailableError):
        selector.select(
            PlanTask(name="research", required_capabilities=["research"]),
            [writer],
            db,
        )


def test_max_agents_limits_selection_pool(db):
    agents = [_agent(f"researcher-{i}", "researcher", status=AgentStatus.ACTIVE) for i in range(5)]
    db.add_all(agents)
    db.commit()
    selector = CapabilityAgentSelector(max_agents=2)
    sel = selector.select(
        PlanTask(name="research", required_capabilities=["research"]),
        agents,
        db,
    )
    # Only two qualified; one of them is selected.
    assert sel.agent_id in {a.id for a in agents[:2]}


def test_selection_is_deterministic(db):
    agents = [_agent("r1", "researcher"), _agent("r2", "researcher")]
    db.add_all(agents)
    db.commit()
    selector = CapabilityAgentSelector()
    task = PlanTask(name="research", required_capabilities=["research"])
    first = selector.select(task, agents, db)
    second = selector.select(task, agents, db)
    assert first.agent_id == second.agent_id


def test_tool_permission_grants_capability(db):
    # Analyst agent; grant it a writing tool permission so capabilities union.
    analyst = _agent("analyst", "analyst")
    db.add(analyst)
    db.commit()
    from app.db.models.agent_tool_permission import AgentToolPermission

    db.add(AgentToolPermission(agent_id=analyst.id, tool_name="text_utils", granted=True))
    db.commit()
    selector = CapabilityAgentSelector()
    sel = selector.select(
        PlanTask(name="write", required_capabilities=["writing"]),
        [analyst],
        db,
    )
    assert sel.agent_id == analyst.id
