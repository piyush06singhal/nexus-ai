"""Agent communication bus.

The :class:`AgentMessageBus` is the *only* channel through which agents
exchange information during an orchestration — there is no unrestricted direct
pointer between agents (spec §7, §8). Messages are persisted, authorized to the
orchestration, and queryable as a conversation or a point-to-point thread.
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models.orchestration import AgentMessage, AgentMessageType
from app.orchestration.messages import AgentMessagePayload
from app.orchestration.types import CommunicationError


def _dumps(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


class AgentMessageBus:
    """Persists and queries inter-agent messages."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def authorized_agent_ids(self, orchestration_id: UUID) -> set[UUID]:
        """Return the set of agent ids authorized to participate in an
        orchestration (from its tasks/assignments). A sender/recipient must be
        in this set for the message to be accepted (spec §8 authorization)."""
        from app.db.models.orchestration import AgentAssignment, OrchestrationTask

        agent_ids: set[UUID] = set()
        stmt = (
            select(OrchestrationTask.agent_id)
            .where(OrchestrationTask.orchestration_id == orchestration_id)
            .where(OrchestrationTask.agent_id.is_not(None))
        )
        for (agent_id,) in self._db.execute(stmt):
            agent_ids.add(agent_id)
        stmt2 = select(AgentAssignment.agent_id).where(
            AgentAssignment.orchestration_id == orchestration_id
        )
        for (agent_id,) in self._db.execute(stmt2):
            agent_ids.add(agent_id)
        return agent_ids

    def send(self, payload: AgentMessagePayload) -> AgentMessage:
        """Persist a single message, enforcing orchestration authorization.

        A sender or recipient that is not an authorized participant of the
        orchestration causes a :class:`CommunicationError` — preventing one
        agent from posting into an orchestration it does not belong to.
        """
        if isinstance(payload.message_type, str):
            payload.message_type = AgentMessageType(payload.message_type)
        permitted = self.authorized_agent_ids(payload.orchestration_id)
        for participant in (payload.sender_agent_id, payload.recipient_agent_id):
            if participant is not None and participant not in permitted:
                raise CommunicationError(
                    f"Agent {participant!s} is not authorized to participate in "
                    f"orchestration {payload.orchestration_id!s}"
                )
        message = AgentMessage(
            orchestration_id=payload.orchestration_id,
            sender_agent_id=payload.sender_agent_id,
            recipient_agent_id=payload.recipient_agent_id,
            message_type=payload.message_type,
            content=payload.content,
            metadata_json=_dumps(payload.metadata),
            correlation_id=payload.correlation_id,
            task_id=payload.task_id,
        )
        self._db.add(message)
        self._db.commit()
        self._db.refresh(message)
        return message

    def receive_inbox(
        self, agent_id: UUID, *, orchestration_id: UUID | None = None
    ) -> list[AgentMessage]:
        """Return the inbox for an agent (messages addressed to it).

        Optionally scoped to an orchestration. A message with ``None``
        recipient is a broadcast visible to every participant.
        """
        stmt = select(AgentMessage).order_by(AgentMessage.created_at)
        if orchestration_id is not None:
            stmt = stmt.where(AgentMessage.orchestration_id == orchestration_id)
        rows = list(self._db.scalars(stmt).all())
        return [m for m in rows if m.recipient_agent_id is None or m.recipient_agent_id == agent_id]

    def get_conversation(self, orchestration_id: UUID) -> list[AgentMessage]:
        """Return every message for an orchestration in chronological order."""
        stmt = (
            select(AgentMessage)
            .where(AgentMessage.orchestration_id == orchestration_id)
            .order_by(AgentMessage.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def get_conversation_between(self, a: UUID, b: UUID) -> list[AgentMessage]:
        """Return the point-to-point thread between two agents (either direction)."""
        stmt = (
            select(AgentMessage)
            .where(
                (AgentMessage.sender_agent_id == a) & (AgentMessage.recipient_agent_id == b)
                | (AgentMessage.sender_agent_id == b) & (AgentMessage.recipient_agent_id == a)
            )
            .order_by(AgentMessage.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def get(self, message_id: UUID) -> AgentMessage:
        message = self._db.get(AgentMessage, message_id)
        if message is None:
            raise NotFoundError(f"AgentMessage {message_id} not found")
        return message

    def count(self, orchestration_id: UUID) -> int:
        """Return the number of messages for an orchestration."""
        return len(self.get_conversation(orchestration_id))
