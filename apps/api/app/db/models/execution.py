"""AgentExecution domain model.

A single execution of a Task by an Agent against a model provider. Records
the input, output, model configuration used, token usage, and outcome so
every execution is auditable and reproducible.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.agent import _enum_values
from app.db.session import Base


class ExecutionStatus(StrEnum):
    """Lifecycle status for an agent execution."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentExecution(Base):
    """Records what happened when an agent executed a task.

    Attributes:
        id: Primary key.
        task_id: Foreign key to the task being executed.
        agent_id: Foreign key to the agent that executed the task.
        status: Terminal / in-flight execution status.
        input_data: JSON-serialized input actually sent to the model.
        output_data: JSON-serialized structured output produced by the model.
        error: Error message if the execution failed.
        provider: Provider actually used for the execution.
        model_name: Model actually used for the execution.
        prompt_tokens / completion_tokens / total_tokens: Token usage.
        estimated_cost: Computed cost estimate for the execution.
        latency_ms: Wall-clock duration of the model call.
        metadata_json: Free-form JSON (trace id, raw params, etc.).
    """

    __tablename__ = "agent_executions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        Uuid,
        index=True,
        nullable=False,  # FK added in migration for ordering freedom
    )
    agent_id: Mapped[UUID] = mapped_column(
        Uuid,
        index=True,
        nullable=False,  # FK added in migration for ordering freedom
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(
            ExecutionStatus,
            name="execution_status",
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
        default=ExecutionStatus.RUNNING,
    )
    input_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    output_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AgentExecution id={self.id} status={self.status.value}>"
