"""Pydantic API schemas for agents.

Mirror the ORM :class:`app.db.models.agent.Agent` but remain decoupled from
SQLAlchemy so they can validate API input and serialize API output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.agent import AgentStatus


class AgentBase(BaseModel):
    """Shared fields for agent create/update request payloads."""

    name: str = Field(min_length=1, max_length=128)
    role: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    status: AgentStatus = AgentStatus.DRAFT
    system_prompt: str | None = None
    provider: str = Field(default="openai", max_length=64)
    model_name: str = Field(default="gpt-4o", max_length=128)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    model_params: dict[str, Any] | None = None


class AgentCreate(AgentBase):
    """Payload to create a new agent."""


class AgentUpdate(BaseModel):
    """Partial update payload for an agent. All fields optional."""

    role: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    status: AgentStatus | None = None
    system_prompt: str | None = None
    provider: str | None = Field(default=None, max_length=64)
    model_name: str | None = Field(default=None, max_length=128)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    model_params: dict[str, Any] | None = None


class AgentRead(AgentBase):
    """Full agent representation returned by the API."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
