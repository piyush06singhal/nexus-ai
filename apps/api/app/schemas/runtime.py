"""Schemas for the agent runtime.

``AgentResult`` is the structured, validated output that an agent produces
when executing a task — the contract between the model and the business
layer. It normalizes a model's free-form JSON response into a schema the
caller can trust.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    """Structured output contract for agent task execution.

    Attributes:
        summary: A short human-readable summary of what the agent did.
        output: The primary structured output payload produced by the agent.
        confidence: Optional 0-1 confidence score for the result.
        followup_actions: Optional list of follow-up actions the agent suggests.
    """

    summary: str = Field(min_length=1, description="Short summary of the agent's work")
    output: dict[str, Any] = Field(
        default_factory=dict, description="The structured output payload"
    )
    confidence: float | None = Field(default=None, ge=0, le=1)
    followup_actions: list[str] = Field(default_factory=list)
