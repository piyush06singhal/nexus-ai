"""Pydantic API schemas for tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.task import TaskStatus


class TaskBase(BaseModel):
    """Shared fields for task create/update payloads."""

    title: str = Field(min_length=1, max_length=256)
    description: str | None = None
    input_data: dict[str, Any] | None = Field(
        default=None, description="JSON payload for the agent"
    )
    assigned_agent_id: UUID | None = None


class TaskCreate(TaskBase):
    """Payload to create a new task."""


class TaskRead(TaskBase):
    """Full task representation returned by the API."""

    id: UUID
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
