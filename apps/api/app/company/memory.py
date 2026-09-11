"""AI Company Layer — company/department memory.

Delegates to the existing Phase 4 ``MemoryService`` using a namespace
convention (``company:{company_id}`` / ``department:{department_id}``) and
``owner_type=SYSTEM``. No second vector store. Company memory stores decisions,
policies, lessons, and report summaries as validated structured knowledge;
department memory scopes operational learnings to a department. Permission
control is enforced at the service boundary — a company's memory is never
visible through a department namespace and vice-versa.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.memory import MemoryOwnerType, MemoryStatus, MemoryType
from app.schemas.memory import MemoryCreate
from app.services.memory_service import MemoryService, to_dict


def _canonical_namespace(kind: str, entity_id: UUID) -> str:
    return f"{kind}:{str(entity_id)}"


class CompanyMemoryService:
    """Store and query memories scoped to a company or department."""

    def __init__(self, db: Session, memory_service: MemoryService | None = None) -> None:
        self._db = db
        # Fresh service per construction to avoid sharing session state.
        self._memory = memory_service or MemoryService(db)

    # ── Company scope ────────────────────────────────────────────────

    @property
    def company_ns(self) -> str:
        return _canonical_namespace("company", UUID(int=0))

    def store_company_memory(
        self,
        *,
        company_id: UUID,
        memory_type: MemoryType,
        content: str,
        summary: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store a validated structured memory under the company namespace."""
        namespace = _canonical_namespace("company", company_id)
        payload = MemoryCreate(
            namespace=namespace,
            type=memory_type,
            content=content,
            summary=summary,
            owner_type=MemoryOwnerType.SYSTEM,
            metadata_json=metadata_json or {},
        )
        memory = self._memory.create(payload)
        return to_dict(memory)

    def list_company_memories(
        self, company_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        namespace = _canonical_namespace("company", company_id)
        memories, _total = self._memory.list(
            namespace=namespace,
            owner_type=MemoryOwnerType.SYSTEM,
            status=MemoryStatus.ACTIVE,
            limit=limit,
            offset=offset,
        )
        return [to_dict(m) for m in memories]

    def search_company_memories(
        self, company_id: UUID, query: str, *, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Semantic search over company memories (delegates to memory search)."""
        from app.schemas.memory import MemorySearchRequest

        namespace = _canonical_namespace("company", company_id)
        request = MemorySearchRequest(
            query=query,
            namespace=namespace,
            top_k=limit,
        )
        return asyncio.run(self._memory.search(request))

    def delete_company_memories(self, company_id: UUID) -> int:
        """Archive all memories in the company namespace."""
        namespace = _canonical_namespace("company", company_id)
        memories, _total = self._memory.list(
            namespace=namespace,
            owner_type=MemoryOwnerType.SYSTEM,
            limit=1000,
        )
        for m in memories:
            self._memory.archive(m.id)
        return len(memories)

    # ── Department scope ─────────────────────────────────────────────

    def store_department_memory(
        self,
        *,
        department_id: UUID,
        memory_type: MemoryType,
        content: str,
        summary: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        namespace = _canonical_namespace("department", department_id)
        payload = MemoryCreate(
            namespace=namespace,
            type=memory_type,
            content=content,
            summary=summary,
            owner_type=MemoryOwnerType.SYSTEM,
            metadata_json=metadata_json or {},
        )
        memory = self._memory.create(payload)
        return to_dict(memory)

    def list_department_memories(
        self, department_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        namespace = _canonical_namespace("department", department_id)
        memories, _total = self._memory.list(
            namespace=namespace,
            owner_type=MemoryOwnerType.SYSTEM,
            status=MemoryStatus.ACTIVE,
            limit=limit,
            offset=offset,
        )
        return [to_dict(m) for m in memories]

    def search_department_memories(
        self, department_id: UUID, query: str, *, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Semantic search over department memories."""
        from app.schemas.memory import MemorySearchRequest

        namespace = _canonical_namespace("department", department_id)
        request = MemorySearchRequest(
            query=query,
            namespace=namespace,
            top_k=limit,
        )
        return asyncio.run(self._memory.search(request))

    def delete_department_memories(self, department_id: UUID) -> int:
        """Archive all memories in the department namespace."""
        namespace = _canonical_namespace("department", department_id)
        memories, _total = self._memory.list(
            namespace=namespace,
            owner_type=MemoryOwnerType.SYSTEM,
            limit=1000,
        )
        for m in memories:
            self._memory.archive(m.id)
        return len(memories)
