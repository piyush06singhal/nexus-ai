"""Agent message contracts.

The :class:`AgentMessageType` enum mirrors the DB column's allowed message
types. :class:`AgentMessagePayload` is the transport object the bus persists;
it carries provenance (sender/recipient agents), a correlation id for threading,
and optional task linkage. All communication between agents flows through the
bus as :class:`AgentMessagePayload` instances (spec §7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.db.models.orchestration import AgentMessageType

__all__ = ["AgentMessageType", "AgentMessagePayload"]


@dataclass
class AgentMessagePayload:
    """A single message to persist on the agent communication bus."""

    orchestration_id: UUID
    message_type: AgentMessageType
    content: str
    sender_agent_id: UUID | None = None  # None = system/orchestrator
    recipient_agent_id: UUID | None = None  # None = broadcast
    correlation_id: UUID | None = field(default_factory=uuid4)
    metadata: dict | None = None
    task_id: UUID | None = None
