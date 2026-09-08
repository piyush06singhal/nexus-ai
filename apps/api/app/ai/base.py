"""Base class for model providers.

Provides shared plumbing (default option handling, model resolution) so
concrete providers only implement the actual calls to their SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.ai.types import ChatMessage, GenerationOptions, ModelResponse


class BaseModelProvider(ABC):
    """Opinionated base for concrete provider adapters."""

    #: Unique provider identifier, e.g. ``"openai"``.
    name: str

    #: Default model identifier and temperature used when a call does not
    #: specify an override.
    default_model: str
    default_temperature: float = 0.7
    default_max_tokens: int = 4096

    def __init__(
        self,
        *,
        default_model: str | None = None,
        default_temperature: float | None = None,
    ) -> None:
        if default_model:
            self.default_model = default_model
        if default_temperature is not None:
            self.default_temperature = default_temperature

    def _resolve_model(self, options: GenerationOptions | None) -> str:
        """Return the effective model for a call, falling back to default."""
        if options is not None and options.model:
            return options.model
        return self.default_model

    @abstractmethod
    def generate(
        self,
        messages: list[ChatMessage],
        *,
        options: GenerationOptions | None = None,
    ) -> ModelResponse:
        """Return a complete (non-streamed) model response."""
        raise NotImplementedError

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        *,
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        """Yield response content tokens incrementally."""
        raise NotImplementedError

    def structured_output(
        self,
        messages: list[ChatMessage],
        *,
        schema: type,
        options: GenerationOptions | None = None,
    ) -> object:
        """Return a response validated against the given Pydantic schema.

        Concrete providers may override this with a native structured-output
        path; the default implementation JSON-parses ``generate`` and
        validates against ``schema``.
        """
        response = self.generate(messages, options=options)
        import json

        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError("Provider returned non-JSON for structured output") from exc
        return schema.model_validate(parsed)
