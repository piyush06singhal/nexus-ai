"""ToolCall domain model.

Records a single tool invocation within an agent execution. Each tool call
is a row in the ``tool_calls`` table, linked to the parent execution.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.agent import _enum_values
from app.db.session import Base


class ToolCallStatus(StrEnum):
    """Outcome status of a single tool call."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    DENIED = "denied"


class ToolCallRecord(Base):
    """A single tool invocation within an agent execution.

    Attributes:
        id: Primary key.
        execution_id: Foreign key to the parent agent execution.
        tool_name: Name of the tool that was called.
        arguments: JSON-serialized arguments supplied by the agent.
        result_status: Outcome of the call.
        result_data: JSON-serialized tool output (when successful).
        result_error: Error message (when not successful).
        execution_time_ms: Wall-clock duration of the tool call.
        iteration: Which iteration of the tool loop this call occurred in.
    """

    __tablename__ = "tool_calls"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(Uuid, index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    result_status: Mapped[ToolCallStatus] = mapped_column(
        Enum(
            ToolCallStatus,
            name="tool_call_status",
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    result_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    result_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ToolCall id={self.id} tool={self.tool_name!r} status={self.result_status.value}>"
