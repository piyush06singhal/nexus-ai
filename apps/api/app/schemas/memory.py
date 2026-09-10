"""Pydantic API schemas for memory.

Mirror the ORM :class:`app.db.models.memory.Memory` while remaining decoupled
from SQLAlchemy so they validate input and serialize output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.memory import (
    MemoryOwnerType,
    MemorySourceType,
    MemoryStatus,
    MemoryType,
)


class MemoryCreate(BaseModel):
    """Payload to create a new memory."""

    namespace: str = Field(min_length=1, max_length=128)
    type: MemoryType
    content: str = Field(min_length=1)
    summary: str | None = Field(default=None, max_length=256)
    owner_type: MemoryOwnerType = MemoryOwnerType.SYSTEM
    owner_id: UUID | None = None
    source_type: MemorySourceType | None = None
    source_id: UUID | None = None
    importance: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=1.0, ge=0, le=1)
    metadata_json: dict[str, Any] | None = None
    expires_at: datetime | None = None


class MemoryUpdate(BaseModel):
    """Partial update payload for a memory. All fields optional."""

    content: str | None = Field(default=None, min_length=1)
    summary: str | None = Field(default=None, max_length=256)
    status: MemoryStatus | None = None
    importance: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    expires_at: datetime | None = None


class MemoryRead(BaseModel):
    """Full memory representation returned by the API."""

    id: UUID
    namespace: str
    type: MemoryType
    owner_type: MemoryOwnerType
    owner_id: UUID | None
    status: MemoryStatus
    source_type: MemorySourceType | None
    source_id: UUID | None
    content: str
    summary: str | None
    metadata_json: dict[str, Any] | None
    confidence: float
    importance: float
    access_count: int
    last_accessed_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryListResponse(BaseModel):
    """Paginated memory listing."""

    memories: list[MemoryRead]
    total: int


class MemorySearchRequest(BaseModel):
    """Payload to search memories with hybrid retrieval."""

    query: str = Field(min_length=1)
    namespace: str = Field(min_length=1, max_length=128)
    owner_id: UUID | None = None
    memory_types: list[MemoryType] | None = None
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0, le=1)


class MemorySearchResult(BaseModel):
    """A single scored memory from a search."""

    memory: MemoryRead
    score: float
    breakdown: dict[str, float]


class MemoryCleanupResponse(BaseModel):
    """Result of a TTL-expiry cleanup run."""

    expired_count: int
