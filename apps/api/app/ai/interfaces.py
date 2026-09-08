"""Model provider interface.

The ``ModelProvider`` Protocol is the contract that all concrete provider
adapters (OpenAI, Anthropic, Gemini, local, …) must satisfy. Business logic
depends on this interface — never on a provider's SDK directly — which keeps
the application vendor-agnostic and testable with mocks.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, TypeVar, runtime_checkable

from app.ai.types import ChatMessage, GenerationOptions, ModelResponse

T = TypeVar("T")


@runtime_checkable
class ModelProvider(Protocol):
    """A normalized interface for calling an LLM provider."""

    #: Unique provider identifier, e.g. ``"openai"``, ``"anthropic"``.
    name: str

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        options: GenerationOptions | None = None,
    ) -> ModelResponse:
        """Return a complete (non-streamed) model response."""
        ...

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        """Yield response content tokens incrementally."""
        ...

    def structured_output(
        self,
        messages: list[ChatMessage],
        *,
        schema: type[T],
        options: GenerationOptions | None = None,
    ) -> T:
        """Return a response validated against the given Pydantic schema."""
        ...
