"""Stub model provider.

A minimal, dependency-free provider that returns canned output. It exists so
the abstraction layer and DI seam can be exercised without any network call
or API key. It will be replaced by real provider adapters in Phase 1+.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.ai.base import BaseModelProvider
from app.ai.types import ChatMessage, GenerationOptions, ModelResponse


class OpenAIProvider(BaseModelProvider):
    """Phase 0 stub for the OpenAI provider adapter.

    Does not call the OpenAI SDK. When ``stub_enabled`` is set, ``generate``
    returns a deterministic canned response and ``stream`` echoes it token by
    token. SDK integration is deferred to Phase 1.
    """

    name = "openai"
    default_model = "gpt-4o-mini"

    def __init__(
        self,
        *,
        stub_enabled: bool = False,
        default_model: str | None = None,
        default_temperature: float | None = None,
    ) -> None:
        super().__init__(default_model=default_model, default_temperature=default_temperature)
        self.stub_enabled = stub_enabled

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        options: GenerationOptions | None = None,
    ) -> ModelResponse:
        model = self._resolve_model(options)
        if not self.stub_enabled:
            raise NotImplementedError(
                "OpenAIProvider is a Phase 0 stub. Set 'stub_enabled' to use canned output."
            )
        prompt = messages[-1].content if messages else ""
        return ModelResponse(
            content=f"[stub:{self.name}] Received {len(messages)} message(s). Last: {prompt[-60:]}",
            model=model,
            finish_reason="stop",
        )

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        response = self.generate(messages, options=options)
        for token in response.content.split(" "):
            yield token + " "
