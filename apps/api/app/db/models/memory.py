"""Memory domain model (Phase 4).

A single ``memories`` table with a ``type`` discriminator column holds all five
memory kinds the system supports. Memories are scoped by ``namespace`` for
isolation, optionally owned by an agent, and retain provenance back to their
source (e.g. an agent execution) for observability.

Embeddings are stored as text-serialized vectors (a ``[0.1, 0.2, ...]`` JSON
array) so the model has no hard dependency on pgvector. Semantic similarity is
computed in Python by the retrieval layer; pgvector remains a documented
scale optimization for large deployments.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.agent import _enum_values
from app.db.session import Base


class MemoryType(StrEnum):
    """The five memory kinds NEXUS distinguishes."""

    WORKING = "working"  # short-term context (current task state)
    EPISODIC = "episodic"  # past experiences, event sequences
    SEMANTIC = "semantic"  # facts, knowledge, relationships
    PROCEDURAL = "procedural"  # how-to knowledge, skills, patterns
    STRUCTURED = "structured"  # JSON-structured records (entities, relations)


class MemoryStatus(StrEnum):
    """Lifecycle status for a single memory record."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPIRED = "expired"


class MemoryOwnerType(StrEnum):
    """Who owns a memory — an agent or the system."""

    AGENT = "agent"
    SYSTEM = "system"


class MemorySourceType(StrEnum):
    """Where a memory originated."""

    EXECUTION = "execution"
    USER_INPUT = "user_input"
    TOOL_OUTPUT = "tool_output"
    IMPORTED = "imported"


class Memory(Base):
    """A single unit of stored agent memory.

    Attributes:
        id: Primary key.
        namespace: Isolation key (e.g. an org or project scope). Memories in
            different namespaces never see each other.
        type: Which of the five memory kinds this is.
        owner_type: Whether an agent or the system owns this memory.
        owner_id: Agent id when ``owner_type == AGENT``, else ``None``.
        status: active / archived / expired.
        source_type: How the memory was created (e.g. extracted from execution).
        source_id: Provenance id, e.g. the ``AgentExecution`` it came from.
        content: The memory payload text.
        summary: Optional short human label.
        metadata_json: Arbitrary JSON metadata.
        embedding: Text-serialized vector (JSON array of floats) or ``None``.
        confidence: 0-1 belief in correctness of this memory.
        importance: 0-1 significance score.
        access_count: How many times this memory was retrieved.
        last_accessed_at: Last retrieval time.
        expires_at: TTL expiry (used by working memory auto-expiration).
    """

    __tablename__ = "memories"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[MemoryType] = mapped_column(
        Enum(
            MemoryType,
            name="memory_type",
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    owner_type: Mapped[MemoryOwnerType] = mapped_column(
        Enum(
            MemoryOwnerType,
            name="memory_owner_type",
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
        default=MemoryOwnerType.SYSTEM,
    )
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[MemoryStatus] = mapped_column(
        Enum(
            MemoryStatus,
            name="memory_status",
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
        default=MemoryStatus.ACTIVE,
    )
    source_type: Mapped[MemorySourceType | None] = mapped_column(
        Enum(
            MemorySourceType,
            name="memory_source_type",
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=False,
        ),
        nullable=True,
    )
    source_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON vector
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_memories_namespace", "namespace"),
        Index("ix_memories_namespace_owner", "namespace", "owner_id"),
        Index("ix_memories_namespace_type", "namespace", "type"),
        Index("ix_memories_namespace_status", "namespace", "status"),
        Index("ix_memories_expiry", "expires_at", "status"),
        Index("ix_memories_namespace_created", "namespace", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Memory id={self.id} type={self.type.value} ns={self.namespace!r}>"
