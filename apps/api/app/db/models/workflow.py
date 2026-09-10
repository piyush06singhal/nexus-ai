"""Workflow domain models.

Phase 3 — Workflow Orchestration. A ``Workflow`` is a durable, versioned graph
of ``WorkflowStep`` instances coordinated by a worker/scheduler. Each run of a
workflow produces a ``WorkflowExecution`` that records per-step
``StepExecution`` records. ``WorkflowTrigger`` instances (schedule, event,
webhook) define when a workflow runs.

All step config, dependencies, and retry policies are stored as JSON blobs so
the orchestration layer stays schema-flexible while the relational columns
carry identity, ordering, and lifecycle state.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
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


class WorkflowStatus(StrEnum):
    """Lifecycle status for a workflow."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class WorkflowStepType(StrEnum):
    """The kind of operation a workflow step performs."""

    AGENT_TASK = "agent_task"
    TOOL_ACTION = "tool_action"
    CONDITION = "condition"
    DELAY = "delay"
    ORCHESTRATION = "orchestration"


class WorkflowExecutionStatus(StrEnum):
    """Lifecycle status for a single workflow execution."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class StepStatus(StrEnum):
    """Lifecycle status for a single step within an execution."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TriggerType(StrEnum):
    """The kind of trigger that kicks off a workflow run."""

    SCHEDULE = "schedule"
    EVENT = "event"
    WEBHOOK = "webhook"


class IdempotencyTag(StrEnum):
    """How safe a step is to re-run; gates automatic retry.

    ``read_only`` and ``idempotent`` steps may be auto-retried. ``side_effecting``
    and ``non_idempotent`` steps are never auto-retried to avoid double effects.
    """

    READ_ONLY = "read_only"
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"
    SIDE_EFFECTING = "side_effecting"


def _enum_column(enum_cls, name: str):
    """Build a reusable ``Enum`` column using the project's enum convention."""
    return Enum(
        enum_cls,
        name=name,
        values_callable=_enum_values,
        native_enum=False,
        create_constraint=False,
    )


class Workflow(Base):
    """A durable, versioned, multi-step orchestration definition.

    Attributes:
        name: Unique human-readable identifier.
        description: Free-text summary of the workflow's purpose.
        status: Lifecycle status (draft / active / paused / archived).
        version: Increments as the definition changes.
        configuration: Free-form JSON blob for workflow-level settings.
    """

    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        _enum_column(WorkflowStatus, "workflow_status"),
        nullable=False,
        default=WorkflowStatus.DRAFT,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    configuration: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Workflow id={self.id} name={self.name!r} status={self.status.value}>"


class WorkflowStep(Base):
    """A single operation within a workflow's dependency graph.

    Attributes:
        name: Unique name within the workflow — used as the key for
            cross-step data references (e.g. ``steps.<name>.output``).
        step_type: agent_task / tool_action / condition / delay.
        configuration: JSON blob, type-specific (agent_id, tool_name, input
            mapping, delay seconds, etc.).
        order: Numeric ordering used as a tiebreaker alongside dependencies.
        dependencies: JSON list of step names this step depends on.
        timeout_seconds: Hard wall-clock bound before the step is timed out.
        retry_policy: JSON ``{max_attempts, backoff, delay, retry_on}``.
        idempotency: Retry-safety tag (see :class:`IdempotencyTag`).
    """

    __tablename__ = "workflow_steps"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_type: Mapped[WorkflowStepType] = mapped_column(
        _enum_column(WorkflowStepType, "workflow_step_type"),
        nullable=False,
    )
    configuration: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_policy: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    idempotency: Mapped[IdempotencyTag] = mapped_column(
        _enum_column(IdempotencyTag, "idempotency_tag"),
        nullable=False,
        default=IdempotencyTag.NON_IDEMPOTENT,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_workflow_steps_workflow_name", "workflow_id", "name"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WorkflowStep id={self.id} name={self.name!r} type={self.step_type.value}>"


class WorkflowTrigger(Base):
    """Defines when a workflow runs (schedule, event, or webhook).

    Attributes:
        trigger_type: schedule / event / webhook.
        configuration: JSON blob — for schedule: ``{interval|next_run_at}``;
            for event: ``{event_name}``; for webhook: ``{webhook_secret}``.
        enabled: Whether the trigger is currently active.
        next_run_at: For schedule triggers, when the next run fires. The
            scheduler polls this column and advances it after each firing.
    """

    __tablename__ = "workflow_triggers"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        _enum_column(TriggerType, "workflow_trigger_type"),
        nullable=False,
    )
    configuration: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_workflow_triggers_next_run", "enabled", "next_run_at"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WorkflowTrigger id={self.id} type={self.trigger_type.value}>"


class WorkflowExecution(Base):
    """A single run of a workflow, coordinating all of its steps.

    Attributes:
        status: queued / running / completed / failed / cancelled / timed_out.
        trigger_type: What kicked off this run (schedule / event / webhook / manual).
        input_data: JSON blob passed in as the workflow's starting context.
        output_data: JSON blob of the workflow's final structured output.
        error: Message if the run failed or timed out.
        duration_ms: Wall-clock duration of the run once terminal.
    """

    __tablename__ = "workflow_executions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[WorkflowExecutionStatus] = mapped_column(
        _enum_column(WorkflowExecutionStatus, "workflow_execution_status"),
        nullable=False,
        default=WorkflowExecutionStatus.QUEUED,
    )
    trigger_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    output_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_workflow_executions_status", "status"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WorkflowExecution id={self.id} status={self.status.value}>"


class StepExecution(Base):
    """Records what happened when a workflow ran one of its steps.

    Attributes:
        status: pending / ready / running / completed / failed / skipped /
            cancelled / timed_out.
        input_data: JSON blob actually passed into the step.
        output_data: JSON blob produced by the step.
        attempt_number: Which retry attempt this represents (1-based).
    """

    __tablename__ = "step_executions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_execution_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_step_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_steps.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[StepStatus] = mapped_column(
        _enum_column(StepStatus, "step_status"),
        nullable=False,
        default=StepStatus.PENDING,
    )
    input_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    output_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_step_executions_workflow_step",
            "workflow_execution_id",
            "workflow_step_id",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<StepExecution id={self.id} status={self.status.value}>"
