"""Agent domain model.

Phase 1 expands the Phase 0 stub with role, system prompt, status, and
model configuration fields for the agent runtime.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _enum_values(enum_cls) -> list[str]:
    """Return the boxed *values* (lowercase) for a StrEnum.

    Used so the ORM stores "active"/"pending" rather than "ACTIVE"/"PENDING",
    keeping DB columns consistent with the migration's String columns and
    ``server_default`` values.
    """
    return [m.value for m in enum_cls]


class AgentStatus(StrEnum):
    """Lifecycle status for an agent."""

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"


class Agent(Base):
    """Represents an individual AI agent within the workforce.

    Attributes:
        name: Unique human-readable identifier.
        role: Functional role (e.g. "analyst", "coder", "researcher").
        description: Free-text summary of the agent's purpose.
        status: Lifecycle status (draft / active / inactive).
        system_prompt: Base system instructions baked into every execution.
        provider: AI model provider name (e.g. "openai", "anthropic").
        model_name: Model identifier within the provider (e.g. "gpt-4o").
        temperature: Sampling temperature override (None = provider default).
        max_tokens: Max output tokens override (None = provider default).
        model_params: Extra provider-specific JSON parameters.
    """

    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(
            AgentStatus,
            name="agent_status",
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
        default=AgentStatus.DRAFT,
    )
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="openai")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, default="gpt-4o")
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_params: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Agent id={self.id} name={self.name!r} status={self.status.value}>"
