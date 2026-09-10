"""Tests for the agent communication bus (spec §7, §8, §33)."""

from __future__ import annotations

import uuid

import pytest

from app.db.models.orchestration import (
    AgentMessage,
    AgentMessageType,
    OrchestrationTask,
)
from app.orchestration.bus import AgentMessageBus
from app.orchestration.messages import AgentMessagePayload
from app.orchestration.types import CommunicationError
from app.services.orchestration_service import OrchestrationService


@pytest.fixture
def orchestration(db):
    return OrchestrationService(db).create(
        __import__(
            "app.schemas.orchestration", fromlist=["OrchestrationCreate"]
        ).OrchestrationCreate(objective="bus test")
    )


def test_send_persists_message(db, orchestration):
    agent = uuid.uuid4()
    orch_task = OrchestrationTask(orchestration_id=orchestration.id, name="t1", agent_id=agent)
    db.add(orch_task)
    db.commit()
    bus = AgentMessageBus(db)
    msg = bus.send(
        AgentMessagePayload(
            orchestration_id=orchestration.id,
            message_type=AgentMessageType.STATUS_UPDATE,
            content="hello",
            sender_agent_id=agent,
        )
    )
    assert msg.message_type == AgentMessageType.STATUS_UPDATE
    assert db.get(AgentMessage, msg.id).content == "hello"


def test_broadcast_visible_in_inbox_to_participant(db, orchestration):
    agent_a = uuid.uuid4()
    agent_b = uuid.uuid4()
    db.add(OrchestrationTask(orchestration_id=orchestration.id, name="a", agent_id=agent_a))
    db.add(OrchestrationTask(orchestration_id=orchestration.id, name="b", agent_id=agent_b))
    db.commit()
    bus = AgentMessageBus(db)
    bus.send(
        AgentMessagePayload(
            orchestration_id=orchestration.id,
            message_type=AgentMessageType.INFORMATION_RESPONSE,
            content="for everyone",
            sender_agent_id=agent_a,
            recipient_agent_id=None,  # broadcast
        )
    )
    inbox = bus.receive_inbox(agent_b, orchestration_id=orchestration.id)
    assert any(m.content == "for everyone" for m in inbox)


def test_point_to_point_thread(db, orchestration):
    agent_a = uuid.uuid4()
    agent_b = uuid.uuid4()
    db.add(OrchestrationTask(orchestration_id=orchestration.id, name="a", agent_id=agent_a))
    db.add(OrchestrationTask(orchestration_id=orchestration.id, name="b", agent_id=agent_b))
    db.commit()
    bus = AgentMessageBus(db)
    bus.send(
        AgentMessagePayload(
            orchestration_id=orchestration.id,
            message_type=AgentMessageType.REQUEST_INFORMATION,
            content="q1",
            sender_agent_id=agent_a,
            recipient_agent_id=agent_b,
        )
    )
    bus.send(
        AgentMessagePayload(
            orchestration_id=orchestration.id,
            message_type=AgentMessageType.INFORMATION_RESPONSE,
            content="a1",
            sender_agent_id=agent_b,
            recipient_agent_id=agent_a,
        )
    )
    thread = bus.get_conversation_between(agent_a, agent_b)
    assert [m.content for m in thread] == ["q1", "a1"]


def test_unauthorized_agent_cannot_send(db, orchestration):
    outsider = uuid.uuid4()
    db.add(OrchestrationTask(orchestration_id=orchestration.id, name="a", agent_id=uuid.uuid4()))
    db.commit()
    bus = AgentMessageBus(db)
    with pytest.raises(CommunicationError):
        bus.send(
            AgentMessagePayload(
                orchestration_id=orchestration.id,
                message_type=AgentMessageType.STATUS_UPDATE,
                content="intrusion",
                sender_agent_id=outsider,
            )
        )


def test_unauthorized_recipient_rejected(db, orchestration):
    agent = uuid.uuid4()
    outsider = uuid.uuid4()
    db.add(OrchestrationTask(orchestration_id=orchestration.id, name="a", agent_id=agent))
    db.commit()
    bus = AgentMessageBus(db)
    with pytest.raises(CommunicationError):
        bus.send(
            AgentMessagePayload(
                orchestration_id=orchestration.id,
                message_type=AgentMessageType.STATUS_UPDATE,
                content="to outsider",
                sender_agent_id=agent,
                recipient_agent_id=outsider,
            )
        )


def test_conversation_ordered_chronologically(db, orchestration):
    agent = uuid.uuid4()
    db.add(OrchestrationTask(orchestration_id=orchestration.id, name="a", agent_id=agent))
    db.commit()
    bus = AgentMessageBus(db)
    for i in range(3):
        bus.send(
            AgentMessagePayload(
                orchestration_id=orchestration.id,
                message_type=AgentMessageType.STATUS_UPDATE,
                content=f"msg-{i}",
                sender_agent_id=agent,
            )
        )
    conversation = bus.get_conversation(orchestration.id)
    assert [m.content for m in conversation] == ["msg-0", "msg-1", "msg-2"]


def test_correlation_id_threading(db, orchestration):
    agent = uuid.uuid4()
    db.add(OrchestrationTask(orchestration_id=orchestration.id, name="a", agent_id=agent))
    db.commit()
    bus = AgentMessageBus(db)
    corr = uuid.uuid4()
    bus.send(
        AgentMessagePayload(
            orchestration_id=orchestration.id,
            message_type=AgentMessageType.REQUEST_INFORMATION,
            content="q",
            sender_agent_id=agent,
            correlation_id=corr,
        )
    )
    bus.send(
        AgentMessagePayload(
            orchestration_id=orchestration.id,
            message_type=AgentMessageType.INFORMATION_RESPONSE,
            content="a",
            sender_agent_id=agent,
            correlation_id=corr,
        )
    )
    conversation = bus.get_conversation(orchestration.id)
    assert all(m.correlation_id == corr for m in conversation)
