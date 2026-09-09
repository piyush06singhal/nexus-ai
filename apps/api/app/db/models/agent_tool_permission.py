"""AgentToolPermission domain model.

Controls which tools each agent is permitted to use. An empty permission
set means the agent may use all non-dangerous tools. A populated set
restricts the agent to only the listed tools.

This is a simple Phase 2 permission model; Phase 6 adds full RBAC.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AgentToolPermission(Base):
    """Per-agent tool permission record.

    Attributes:
        id: Primary key.
        agent_id: Foreign key to the agent this permission applies to.
        tool_name: Name of the tool this permission grants or denies.
        granted: If True, the agent is allowed to use the tool.
            If False, the agent is explicitly denied.
    """

    __tablename__ = "agent_tool_permissions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(Uuid, index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<AgentToolPermission agent={self.agent_id} "
            f"tool={self.tool_name!r} granted={self.granted}>"
        )
