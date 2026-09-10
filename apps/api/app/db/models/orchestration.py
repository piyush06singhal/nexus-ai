"""Multi-agent orchestration domain models (Phase 5).

A set of tables that record a single multi-agent orchestration run end-to-end:

- ``orchestrations`` — the top-level objective + lifecycle + final result.
- ``orchestration_tasks`` — the execution plan's decomposed tasks (capabilities,
  dependencies, status, per-task output).
- ``agent_assignments`` — an agent assigned to a specific task (instructions,
  priority, status, execution link).
- ``agent_messages`` — the controlled, persisted inter-agent communication bus.
- ``orchestration_results`` — aggregated raw + structured results per agent/task.
- ``orchestration_context`` — shared facts / decisions / constraints built up
  across the run (selective context, never a whole-state copy).
- ``agent_reviews`` — agent-to-agent review requests and verdicts.

All lifecycle status is governed by :mod:`app.orchestration.state_machine`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.agent import _enum_values
from app.db.session import Base


class OrchestrationStatus(StrEnum):
    """Lifecycle status for an orchestration run."""

    CREATED = "created"
    PLANNING = "planning"
    PLANNED = "planned"
    ASSIGNING = "assigning"
    RUNNING = "running"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrchestrationTaskStatus(StrEnum):
    """Lifecycle status for a single decomposed task."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class AssignmentStatus(StrEnum):
    """Lifecycle status for an agent assignment."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class AgentMessageType(StrEnum):
    """The kind of message exchanged between agents (or orchestrator↔agent)."""

    TASK_ASSIGNMENT = "task_assignment"
    TASK_RESULT = "task_result"
    REQUEST_INFORMATION = "request_information"
    INFORMATION_RESPONSE = "information_response"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    REVIEW_REQUEST = "review_request"
    REVIEW_RESULT = "review_result"


class ReviewVerdict(StrEnum):
    """Outcome of an agent review."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REQUEST_REVISION = "request_revision"


def _enum_column(enum_cls, name: str):
    """Build a reusable ``Enum`` column using the project's enum convention."""
    return Enum(
        enum_cls,
        name=name,
        values_callable=_enum_values,
        native_enum=False,
        create_constraint=False,
    )


class Orchestration(Base):
    """A single multi-agent run toward a shared objective."""

    __tablename__ = "orchestrations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OrchestrationStatus] = mapped_column(
        _enum_column(OrchestrationStatus, "orchestration_status"),
        nullable=False,
        default=OrchestrationStatus.CREATED,
    )
    strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="deterministic")
    selected_agents: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    execution_graph: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    final_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    verification_policy: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_orchestrations_status", "status"),
        Index("ix_orchestrations_created", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Orchestration id={self.id} status={self.status.value}>"


class OrchestrationTask(Base):
    """A decomposed task within an orchestration's execution plan."""

    __tablename__ = "orchestration_tasks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    orchestration_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("orchestrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_capabilities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    status: Mapped[OrchestrationTaskStatus] = mapped_column(
        _enum_column(OrchestrationTaskStatus, "orchestration_task_status"),
        nullable=False,
        default=OrchestrationTaskStatus.PENDING,
    )
    agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    input_context: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    output_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "ix_orchestration_tasks_orchestration",
            "orchestration_id",
            "status",
        ),
        Index("ix_orchestration_tasks_agent", "agent_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OrchestrationTask id={self.id} name={self.name!r} status={self.status.value}>"


class AgentAssignment(Base):
    """An agent assigned to a specific task within an orchestration."""

    __tablename__ = "agent_assignments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    orchestration_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("orchestrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("orchestration_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    status: Mapped[AssignmentStatus] = mapped_column(
        _enum_column(AssignmentStatus, "assignment_status"),
        nullable=False,
        default=AssignmentStatus.PENDING,
    )
    input_context: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    output_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    agent_execution_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_agent_assignments_orchestration", "orchestration_id"),
        Index("ix_agent_assignments_agent", "agent_id"),
        Index("ix_agent_assignments_task", "task_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AgentAssignment id={self.id} status={self.status.value}>"


class AgentMessage(Base):
    """A single persisted message between agents (or orchestrator↔agent)."""

    __tablename__ = "agent_messages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    orchestration_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("orchestrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)  # None = system
    recipient_agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)  # None = broadcast
    message_type: Mapped[AgentMessageType] = mapped_column(
        _enum_column(AgentMessageType, "agent_message_type"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, default=uuid4)
    task_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_agent_messages_orchestration_created", "orchestration_id", "created_at"),
        Index("ix_agent_messages_correlation", "correlation_id"),
        Index("ix_agent_messages_recipient", "recipient_agent_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AgentMessage id={self.id} type={self.message_type.value}>"


class OrchestrationResult(Base):
    """An aggregated result produced by an agent for a task/assignment."""

    __tablename__ = "orchestration_results"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    orchestration_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("orchestrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    assignment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # raw result
    structured_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_orchestration_results_orchestration", "orchestration_id"),
        Index("ix_orchestration_results_agent", "agent_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OrchestrationResult id={self.id}>"


class OrchestrationContext(Base):
    """A shared (or agent-scoped) fact/decision/constraint from a run."""

    __tablename__ = "orchestration_context"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    orchestration_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("orchestrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="shared_fact")
    agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)  # None = shared

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_orchestration_context_orchestration", "orchestration_id"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OrchestrationContext id={self.id} key={self.key!r}>"


class AgentReview(Base):
    """An agent-to-agent review request and its verdict."""

    __tablename__ = "agent_reviews"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    orchestration_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("orchestrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reviewer_agent_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reviewee_agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    request_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict: Mapped[ReviewVerdict] = mapped_column(
        _enum_column(ReviewVerdict, "review_verdict"),
        nullable=False,
        default=ReviewVerdict.PENDING,
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_agent_reviews_orchestration", "orchestration_id"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AgentReview id={self.id} verdict={self.verdict.value}>"
