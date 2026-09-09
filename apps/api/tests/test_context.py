"""Tests for the context builder and agent executability helper."""

import json

from app.db.models.agent import Agent, AgentStatus
from app.db.models.task import Task
from app.runtime.context import agent_is_executable, build_context


def _task(*, input_data=None, title="Test task"):
    return Task(
        title=title,
        description="Do the thing",
        input_data=json.dumps(input_data) if input_data is not None else None,
    )


def _agent(**overrides):
    defaults = dict(
        id="11111111-1111-1111-1111-111111111111",
        name="analyst",
        role="analyst",
        status=AgentStatus.ACTIVE,
        system_prompt="Be precise.",
        provider="openai",
        model_name="gpt-4o",
    )
    defaults.update(overrides)
    return Agent(**defaults)


def test_build_context_system_message_includes_role_and_prompt():
    agent = _agent(role="analyst", system_prompt="Be precise.")
    messages = build_context(agent, _task())
    assert messages[0].role == "system"
    assert "analyst" in messages[0].content
    assert "Be precise." in messages[0].content


def test_build_context_user_message_includes_title_and_input():
    agent = _agent()
    messages = build_context(agent, _task(input_data={"key": "value"}))
    user = messages[1]
    assert user.role == "user"
    assert "Test task" in user.content
    assert '"key": "value"' in user.content


def test_build_context_default_system_when_no_role_or_prompt():
    agent = _agent(role=None, system_prompt=None)
    messages = build_context(agent, _task())
    assert "autonomous agent" in messages[0].content


def test_agent_is_executable_active_with_model():
    assert agent_is_executable(
        _agent(status=AgentStatus.ACTIVE, provider="openai", model_name="gpt-4o")
    )


def test_agent_not_executable_when_draft():
    assert not agent_is_executable(_agent(status=AgentStatus.DRAFT))


def test_agent_not_executable_without_model_name():
    assert not agent_is_executable(_agent(model_name=None))
