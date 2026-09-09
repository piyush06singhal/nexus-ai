"""Task domain model.

A Task is a discrete unit of work assigned to a single agent. Executing a
task produces an :class:`AgentExecution` record.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.agent import Agent, _enum_values
from app.db.session import Base


class TaskStatus(StrEnum):
    """Lifecycle status for a task."""

    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(Base):
    """A discrete unit of work assigned to and executed by an agent.

    Attributes:
        id: Primary key.
        title: Human-readable summary.
        description: Optional detailed description.
        input_data: JSON-serialized payload consumed by the agent execution.
        status: Lifecycle status.
        assigned_agent_id: Foreign key to the agent that owns this task.
        agent: Relationship back to the owning agent.
    """

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
        default=TaskStatus.PENDING,
    )
    assigned_agent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="RESTRICT"), nullable=True
    )

    agent: Mapped[Agent | None] = relationship("Agent", foreign_keys=[assigned_agent_id])

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Task id={self.id} title={self.title!r} status={self.status.value}>"
