"""Pydantic schemas for tools and tool calls.

``ToolRead`` is the API response for tool definitions.
``ToolCallRead`` is the API response for persisted tool call records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Tool definition schemas (read-only — tools are registered, not created via API)
# ---------------------------------------------------------------------------


class ToolParameterSchema(BaseModel):
    """Schema for a single tool parameter definition."""

    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None


class ToolRead(BaseModel):
    """Tool definition returned by the API."""

    name: str
    description: str
    parameters: list[ToolParameterSchema] = Field(default_factory=list)
    dangerous: bool = False
    timeout_seconds: float = 30.0
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Tool call schemas (persisted records from the DB)
# ---------------------------------------------------------------------------


class ToolCallRead(BaseModel):
    """A persisted tool call record returned by the API."""

    id: UUID
    execution_id: UUID
    tool_name: str
    arguments: dict[str, Any] | None = None
    result_status: str
    result_data: Any = None
    result_error: str | None = None
    execution_time_ms: float | None = None
    iteration: int = 1
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
