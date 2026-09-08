"""Agent model (Phase 0 stub).

A minimal Agent table that proves the ORM + migration pipeline works.
Full agent behaviour arrives in Phase 1 (Agent Runtime); for now this
only establishes the schema foundation and ID conventions.

Note: This is intentionally the *only* table in Phase 0. Entities such as
users, organizations, tasks, missions, tools, executions, memories,
approvals, and evaluations will be added incrementally in later phases.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Agent(Base):
    """A single AI agent."""

    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Agent id={self.id} name={self.name!r}>"
