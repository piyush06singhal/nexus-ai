"""Pydantic API schemas for multi-agent orchestration (Phase 5).

Mirror the ORM models in :mod:`app.db.models.orchestration` but stay decoupled
from SQLAlchemy so they can validate API input and serialize API output.

Free-form JSON fields (``execution_graph``, ``final_result``, ``metrics``,
``structured_data``, etc.) are exposed as ``dict[str, Any] | None``; the
``*_to_dict`` serializers in the service handle the DB text ↔ dict round-trip.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.orchestration import (
    AgentMessageType,
    AssignmentStatus,
    OrchestrationStatus,
    OrchestrationTaskStatus,
    ReviewVerdict,
)

# ── Orchestration ─────────────────────────────────────────────────────────────


class OrchestrationCreate(BaseModel):
    """Payload to create a new orchestration run."""

    objective: str = Field(min_length=1)
    strategy: str | None = Field(default=None, max_length=64)
    verification_policy: dict[str, Any] | None = None


class OrchestrationRead(BaseModel):
    """Full orchestration representation returned by the API."""

    id: UUID
    objective: str
    status: OrchestrationStatus
    strategy: str
    selected_agents: list[str] | None = None
    execution_graph: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None
    error: str | None = None
    metrics: dict[str, Any] | None = None
    verification_policy: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrchestrationList(BaseModel):
    """Paginated (simple) list of orchestrations."""

    items: list[OrchestrationRead]
    total: int


# ── Task / assignment / message / result / context / review ──────────────────


class OrchestrationTaskRead(BaseModel):
    """A decomposed task within an orchestration."""

    id: UUID
    orchestration_id: UUID
    name: str
    description: str | None = None
    required_capabilities: list[str] | None = None
    dependencies: list[str] | None = None
    status: OrchestrationTaskStatus
    agent_id: UUID | None = None
    input_context: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    result_summary: str | None = None
    attempt_number: int
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignmentRead(BaseModel):
    """An agent assigned to a task."""

    id: UUID
    orchestration_id: UUID
    task_id: UUID
    agent_id: UUID
    role: str | None = None
    instructions: str | None = None
    priority: int
    dependencies: list[str] | None = None
    status: AssignmentStatus
    input_context: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error: str | None = None
    attempt_number: int
    agent_execution_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MessageRead(BaseModel):
    """A single inter-agent message."""

    id: UUID
    orchestration_id: UUID
    sender_agent_id: UUID | None = None
    recipient_agent_id: UUID | None = None
    message_type: AgentMessageType
    content: str
    metadata: dict[str, Any] | None = None
    correlation_id: UUID | None = None
    task_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrchestrationResultRead(BaseModel):
    """An aggregated result produced by an agent for a task."""

    id: UUID
    orchestration_id: UUID
    task_id: UUID | None = None
    assignment_id: UUID | None = None
    agent_id: UUID | None = None
    content: str | None = None
    structured_data: dict[str, Any] | None = None
    confidence: float | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContextEntryRead(BaseModel):
    """A shared (or agent-scoped) context fact/decision."""

    id: UUID
    orchestration_id: UUID
    key: str
    value: Any | None = None
    kind: str
    agent_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewRead(BaseModel):
    """An agent-to-agent review request and its verdict."""

    id: UUID
    orchestration_id: UUID
    task_id: UUID | None = None
    reviewer_agent_id: UUID
    reviewee_agent_id: UUID | None = None
    request_content: str | None = None
    response_content: str | None = None
    verdict: ReviewVerdict
    iteration: int
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ReviewCreate(BaseModel):
    """Payload to request a review of an agent's output."""

    reviewer_agent_id: UUID
    task_id: UUID | None = None
    reviewee_agent_id: UUID | None = None
    content: str | None = None


class ReviewComplete(BaseModel):
    """Payload to record a verdict for an open review."""

    verdict: ReviewVerdict
    response_content: str | None = None


# ── Timeline ─────────────────────────────────────────────────────────────────


class TimelineEvent(BaseModel):
    """A single observable event in an orchestration's timeline."""

    timestamp: datetime
    event_type: str
    status: str | None = None
    description: str
    entity_id: str | None = None
