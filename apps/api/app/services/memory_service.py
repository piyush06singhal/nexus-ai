"""Memory persistence service.

Provides CRUD, hybrid search, lifecycle (archive / expiry / cleanup), access
tracking, and extraction-on-execution for the memory system. The runtime uses
this to persist and query memories without coupling to the ORM layer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError
from app.db.models.execution import AgentExecution
from app.db.models.memory import (
    Memory,
    MemoryOwnerType,
    MemorySourceType,
    MemoryStatus,
    MemoryType,
)
from app.memory.embedding import EmbeddingProvider
from app.memory.extraction import extract_memories_from_execution
from app.memory.policies import WritePolicy, is_duplicate
from app.memory.retrieval import HybridRetriever
from app.schemas.memory import MemoryCreate, MemorySearchRequest, MemoryUpdate


def _dumps(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return None


class MemoryService:
    """Create, query, and manage memories."""

    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._db = db
        self._provider = embedding_provider

    @property
    def embedding_provider(self) -> EmbeddingProvider | None:
        return self._provider

    # ------------------------------------------------------------------ CRUD

    def create(self, payload: MemoryCreate) -> Memory:
        """Create and persist a memory (embedding attached lazily if desired)."""
        memory = Memory(
            namespace=payload.namespace,
            type=payload.type,
            owner_type=payload.owner_type,
            owner_id=payload.owner_id,
            status=MemoryStatus.ACTIVE,
            source_type=payload.source_type,
            source_id=payload.source_id,
            content=payload.content,
            summary=payload.summary,
            confidence=payload.confidence,
            importance=payload.importance,
            expires_at=payload.expires_at,
            metadata_json=_dumps(payload.metadata_json),
        )
        self._db.add(memory)
        self._db.commit()
        self._db.refresh(memory)
        return memory

    async def ensure_embedding(self, memory: Memory) -> Memory:
        """Compute and store an embedding for *memory* if a provider exists."""
        if self._provider is None or memory.embedding:
            return memory
        text = (memory.summary or "") + " " + memory.content
        vectors = await self._provider.embed([text])
        if vectors:
            memory.embedding = _dumps(vectors[0])
            self._db.commit()
            self._db.refresh(memory)
        return memory

    def get(self, memory_id: UUID) -> Memory:
        memory = self._db.get(Memory, memory_id)
        if memory is None:
            raise NotFoundError(f"Memory {memory_id} not found")
        return memory

    def update(self, memory_id: UUID, payload: MemoryUpdate) -> Memory:
        memory = self.get(memory_id)
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(memory, field, value)
        self._db.commit()
        self._db.refresh(memory)
        return memory

    def delete(self, memory_id: UUID) -> None:
        memory = self.get(memory_id)
        self._db.delete(memory)
        self._db.commit()

    def list(
        self,
        *,
        namespace: str,
        owner_id: UUID | None = None,
        owner_type: MemoryOwnerType | None = None,
        memory_type: MemoryType | None = None,
        status: MemoryStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Memory], int]:
        """Return a ``(memories, total)`` tuple scoped to *namespace*."""
        conditions = [Memory.namespace == namespace]
        if owner_id is not None:
            conditions.append(Memory.owner_id == owner_id)
        if owner_type is not None:
            conditions.append(Memory.owner_type == owner_type)
        if memory_type is not None:
            conditions.append(Memory.type == memory_type)
        if status is not None:
            conditions.append(Memory.status == status)

        total = self._db.scalar(select(func.count(Memory.id)).where(*conditions)) or 0
        stmt = (
            select(Memory)
            .where(*conditions)
            .order_by(Memory.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self._db.scalars(stmt).all()), total

    # ------------------------------------------------------------------ Search

    async def search(self, request: MemorySearchRequest) -> list[dict]:
        """Hybrid search using the retrieval layer; returns serialized results."""
        retriever = HybridRetriever(
            self._db,
            embedding_provider=self._provider,
            settings=settings,
        )
        results = await retriever.retrieve(
            request.query,
            namespace=request.namespace,
            owner_id=request.owner_id,
            memory_types=request.memory_types,
            top_k=request.top_k,
            min_score=request.min_score,
        )
        return [
            {
                "memory": to_dict(r.memory),
                "score": r.score,
                "breakdown": r.breakdown,
            }
            for r in results
        ]

    # ----------------------------------------------------------------- Lifecycle

    def archive(self, memory_id: UUID) -> Memory:
        memory = self.get(memory_id)
        memory.status = MemoryStatus.ARCHIVED
        self._db.commit()
        self._db.refresh(memory)
        return memory

    def expire_working(self, owner_id: UUID, namespace: str) -> int:
        """Expire the owner's working memories that have passed their TTL."""
        now = datetime.now(UTC)
        stmt = select(Memory).where(
            Memory.namespace == namespace,
            Memory.owner_id == owner_id,
            Memory.type == MemoryType.WORKING,
            Memory.status == MemoryStatus.ACTIVE,
            Memory.expires_at.is_not(None),
            Memory.expires_at < now,
        )
        expired = list(self._db.scalars(stmt).all())
        for m in expired:
            m.status = MemoryStatus.EXPIRED
        if expired:
            self._db.commit()
        return len(expired)

    def cleanup_expired(self) -> int:
        """Globally mark every past-due memory as expired; returns count."""
        now = datetime.now(UTC)
        stmt = select(Memory).where(
            Memory.status == MemoryStatus.ACTIVE,
            Memory.expires_at.is_not(None),
            Memory.expires_at < now,
        )
        expired = list(self._db.scalars(stmt).all())
        for m in expired:
            m.status = MemoryStatus.EXPIRED
        if expired:
            self._db.commit()
        return len(expired)

    # ----------------------------------------------------- Reliability hooks

    def store_reliability_memory(
        self,
        *,
        namespace: str,
        kind: str,
        content: str,
        owner_id: UUID | None = None,
        source_id: UUID | None = None,
        importance: float = 0.5,
        metadata_json: dict | None = None,
    ) -> Memory | None:
        """Store zero-or-one semantic/procedural memory from a reliability event.

        Called by the verification/recovery pipeline (Phase 6, §28) so each PASS
        stores one verified-fact memory and each repeated-failure stores one
        failure-pattern / recovered-strategy memory.  Dedups against an existing
        active memory with the same (namespace, kind, owner) so we only keep the
        latest and never flood the store on every execution.

        Args:
            namespace: Memory namespace (e.g. ``"nexus"`` or an owner scope).
            kind: ``"verified_fact"`` for a PASS or ``"recovery_pattern"`` for a
                successful recovery after repeated failure.
            content: The memory content.
            owner_id: Owning agent id, if any.
            source_id: Related execution/task id for traceability.
            importance: Relative importance (0..1).
            metadata_json: Structured evidence (verification/recovery context).

        Returns:
            The new :class:`Memory`, or ``None`` if a duplicate was skipped.
        """
        # Dedup: skip if an active memory already covers the same kind+content.
        stmt = select(Memory).where(
            Memory.namespace == namespace,
            Memory.type.in_((MemoryType.SEMANTIC, MemoryType.PROCEDURAL)),
            Memory.status == MemoryStatus.ACTIVE,
        )
        if owner_id is not None:
            stmt = stmt.where(Memory.owner_id == owner_id)
        for existing in list(self._db.scalars(stmt).all()):
            if existing.content == content:
                return None

        mtype = MemoryType.PROCEDURAL if kind == "recovery_pattern" else MemoryType.SEMANTIC
        memory = Memory(
            namespace=namespace,
            type=mtype,
            owner_type=MemoryOwnerType.AGENT if owner_id else MemoryOwnerType.SYSTEM,
            owner_id=owner_id,
            status=MemoryStatus.ACTIVE,
            source_type=MemorySourceType.EXECUTION if source_id else None,
            source_id=source_id,
            content=content,
            summary=("Verified fact: " if kind != "recovery_pattern" else "Recovery pattern: ")
            + content[:240],
            confidence=1.0,
            importance=importance,
            metadata_json=_dumps({**(metadata_json or {}), "reliability": True}),
        )
        self._db.add(memory)
        self._db.commit()
        self._db.refresh(memory)
        return memory

    # ------------------------------------------------------------- Extraction

    async def extract_and_store(
        self,
        execution: AgentExecution,
        *,
        namespace: str,
        agent_id: UUID,
        used_tools: list[str] | None = None,
    ) -> list[Memory]:
        """Extract and persist memories from a completed execution."""
        memories = await extract_memories_from_execution(
            execution,
            namespace=namespace,
            agent_id=agent_id,
            embedding_provider=self._provider,
            used_tools=used_tools,
        )
        policy = WritePolicy.from_settings(settings)
        stored: list[Memory] = []
        for memory in memories:
            if not self._should_store(memory, policy):
                continue
            self._db.add(memory)
            stored.append(memory)
        if stored:
            self._db.commit()
        return stored

    # -------------------------------------------------------------- Access

    def record_access(self, memory_id: UUID) -> None:
        memory = self.get(memory_id)
        memory.access_count = (memory.access_count or 0) + 1
        memory.last_accessed_at = datetime.now(UTC)
        self._db.commit()

    def record_access_many(self, memory_ids: list[UUID]) -> None:
        for memory_id in memory_ids:
            memory = self._db.get(Memory, memory_id)
            if memory is None:
                continue
            memory.access_count = (memory.access_count or 0) + 1
            memory.last_accessed_at = datetime.now(UTC)
        self._db.commit()

    # ---------------------------------------------------------------- Internals

    def _should_store(self, memory: Memory, policy: WritePolicy) -> bool:
        if memory.importance < policy.min_importance:
            return False
        # Dedup against an existing active memory of the same owner+type.
        existing = self._find_similar(memory, policy)
        if existing and is_duplicate(memory, existing, policy.dedup_threshold):
            return False
        if memory.type == MemoryType.WORKING:
            self._prune_working(memory.owner_id, memory.namespace, policy)
        return True

    def _find_similar(self, memory: Memory, policy: WritePolicy) -> Memory | None:
        stmt = (
            select(Memory)
            .where(
                Memory.namespace == memory.namespace,
                Memory.type == memory.type,
                Memory.status == MemoryStatus.ACTIVE,
                or_(
                    Memory.owner_id == memory.owner_id,
                    Memory.owner_id.is_(None),
                ),
            )
            .order_by(Memory.created_at.desc())
            .limit(20)
        )
        candidates = list(self._db.scalars(stmt).all())
        for candidate in candidates:
            if candidate.id == memory.id:
                continue
            if is_duplicate(memory, candidate, policy.dedup_threshold):
                return candidate
        return None

    def _prune_working(self, owner_id: UUID | None, namespace: str, policy: WritePolicy) -> None:
        stmt = (
            select(Memory)
            .where(
                Memory.namespace == namespace,
                Memory.type == MemoryType.WORKING,
                Memory.status == MemoryStatus.ACTIVE,
                Memory.owner_id == owner_id,
            )
            .order_by(Memory.created_at.asc())
        )
        working = list(self._db.scalars(stmt).all())
        if len(working) <= policy.max_working:
            return
        # Archive the oldest excess working memories.
        excess = working[: len(working) - policy.max_working]
        for m in excess:
            m.status = MemoryStatus.ARCHIVED


def to_dict(memory: Memory) -> dict:
    """Serialize a Memory ORM instance for API responses."""
    return {
        "id": str(memory.id),
        "namespace": memory.namespace,
        "type": memory.type.value,
        "owner_type": memory.owner_type.value,
        "owner_id": str(memory.owner_id) if memory.owner_id else None,
        "status": memory.status.value,
        "source_type": memory.source_type.value if memory.source_type else None,
        "source_id": str(memory.source_id) if memory.source_id else None,
        "content": memory.content,
        "summary": memory.summary,
        "metadata_json": _loads(memory.metadata_json),
        "confidence": memory.confidence,
        "importance": memory.importance,
        "access_count": memory.access_count,
        "last_accessed_at": memory.last_accessed_at,
        "expires_at": memory.expires_at,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }
