"""Memory endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.memory import MemoryOwnerType, MemoryStatus, MemoryType
from app.db.session import get_db
from app.memory.embedding import get_embedding_provider
from app.schemas.memory import (
    MemoryCleanupResponse,
    MemoryCreate,
    MemoryListResponse,
    MemoryRead,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryUpdate,
)
from app.services.memory_service import MemoryService, to_dict

router = APIRouter(tags=["memories"], prefix="/memories")


@router.get("", response_model=MemoryListResponse, summary="List memories in a namespace")
def list_memories(
    namespace: str = Query(..., min_length=1, max_length=128),  # noqa: B008
    owner_id: UUID | None = Query(default=None),  # noqa: B008
    owner_type: MemoryOwnerType | None = Query(default=None),  # noqa: B008
    type: MemoryType | None = Query(default=None, alias="type"),  # noqa: B008
    status: MemoryStatus | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    offset: int = Query(default=0, ge=0),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> MemoryListResponse:
    service = MemoryService(db)
    memories, total = service.list(
        namespace=namespace,
        owner_id=owner_id,
        owner_type=owner_type,
        memory_type=type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return MemoryListResponse(
        memories=[MemoryRead.model_validate(to_dict(m)) for m in memories],
        total=total,
    )


@router.post(
    "",
    response_model=MemoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a memory",
)
async def create_memory(
    payload: MemoryCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> MemoryRead:
    service = MemoryService(db, embedding_provider=get_embedding_provider(settings))
    memory = service.create(payload)
    try:
        await service.ensure_embedding(memory)
    except Exception:  # pragma: no cover - embedding is best-effort
        pass
    return MemoryRead.model_validate(to_dict(memory))


@router.post("/search", response_model=list[MemorySearchResult], summary="Hybrid search memories")
async def search_memories(
    payload: MemorySearchRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[MemorySearchResult]:
    service = MemoryService(db, embedding_provider=get_embedding_provider(settings))
    raw = await service.search(payload)
    return [MemorySearchResult(**item) for item in raw]


@router.post("/cleanup", response_model=MemoryCleanupResponse, summary="Expire past-due memories")
def cleanup_memories(db: Session = Depends(get_db)) -> MemoryCleanupResponse:  # noqa: B008
    service = MemoryService(db)
    expired = service.cleanup_expired()
    return MemoryCleanupResponse(expired_count=expired)


@router.get("/{memory_id}", response_model=MemoryRead, summary="Get a memory")
def get_memory(
    memory_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> MemoryRead:
    service = MemoryService(db)
    return MemoryRead.model_validate(to_dict(service.get(memory_id)))


@router.patch("/{memory_id}", response_model=MemoryRead, summary="Update a memory")
def update_memory(
    memory_id: UUID,
    payload: MemoryUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> MemoryRead:
    service = MemoryService(db)
    memory = service.update(memory_id, payload)
    return MemoryRead.model_validate(to_dict(memory))


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a memory")
def delete_memory(
    memory_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    service = MemoryService(db)
    service.delete(memory_id)


@router.post("/{memory_id}/archive", response_model=MemoryRead, summary="Archive a memory")
def archive_memory(
    memory_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> MemoryRead:
    service = MemoryService(db)
    memory = service.archive(memory_id)
    return MemoryRead.model_validate(to_dict(memory))
