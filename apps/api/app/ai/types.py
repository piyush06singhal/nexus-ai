"""Shared type definitions for the model abstraction layer.

These payload types are provider-agnostic: they are what the rest of the
application passes in and out of a ``ModelProvider``, regardless of which
underlying vendor (OpenAI, Anthropic, Gemini, local) is behind it.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    """A single chat-format message."""

    role: Role
    content: str
    name: str | None = None
    tool_calls: list[Any] | None = None


class TokenUsage(BaseModel):
    """Token usage statistics for a model call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class GenerationOptions(BaseModel):
    """Options controlling a single generation call.

    All fields carry sensible defaults so callers only override what they
    need. ``model`` may be overridden per-call; otherwise the provider's
    configured default model is used.
    """

    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    """The normalized result of a model call.

    Content is always a string. Structured outputs are validated separately
    by ``structured_output``. Timing and usage information support the
    observability goals without leaking provider specifics.
    """

    content: str
    model: str
    finish_reason: str = "stop"
    usage: TokenUsage | None = None
    latency_ms: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
