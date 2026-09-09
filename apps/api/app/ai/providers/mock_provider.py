"""Deterministic mock model provider for testing the agent runtime.

Unlike the OpenAI stub (which is a Phase 0 placeholder), the MockProvider is
a first-class test double used by the runtime and its tests. It produces
deterministic, configurable responses — including malformed output — so
context construction, structured-output parsing, and error handling can be
exercised without any network call or API key.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from app.ai.base import BaseModelProvider
from app.ai.types import ChatMessage, GenerationOptions, ModelResponse, TokenUsage


class MockProvider(BaseModelProvider):
    """A configurable, deterministic provider for tests and local dev.

    Args:
        reply: The raw string ``generate`` returns.
        script: An optional ordered list of raw strings returned across
            successive ``generate`` calls (last one repeats). Used to simulate
            a model that requests a tool call, then returns a final
            ``AgentResult``. Takes precedence over ``reply`` when set.
        usage: Token usage reported on each response.
        raise_error: If set, ``generate`` raises the given exception.
        malformed: If True, ``reply`` is treated as already-invalid JSON so
            callers can test structured-output failure paths.
    """

    name = "mock"

    def __init__(
        self,
        *,
        reply: str = '{"summary": "ok", "output": {}}',
        script: list[str] | None = None,
        usage: TokenUsage | None = None,
        raise_error: Exception | None = None,
        default_model: str = "mock-model",
        default_temperature: float = 0.7,
    ) -> None:
        super().__init__(
            default_model=default_model,
            default_temperature=default_temperature,
        )
        self.reply = reply
        self.script = script
        self.usage = usage or TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        self.raise_error = raise_error
        self._calls = 0
        self.last_messages: list[ChatMessage] | None = None
        self.last_options: GenerationOptions | None = None

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        options: GenerationOptions | None = None,
    ) -> ModelResponse:
        self.last_messages = list(messages)
        self.last_options = options
        if self.raise_error is not None:
            raise self.raise_error

        if self.script:
            # Scripted responses play in order for the first N calls, then the
            # final entry repeats. This lets a mock "request a tool, observe the
            # result, then answer."
            index = min(self._calls, len(self.script) - 1)
            self._calls += 1
            content = self.script[index]
        else:
            content = self.reply

        return ModelResponse(
            content=content,
            model=self._resolve_model(options),
            finish_reason="stop",
            usage=self.usage,
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

    @classmethod
    def json_preview(cls) -> MockProvider:
        """Return a provider that responds with representative AgentResult JSON."""
        return cls(
            reply=json.dumps(
                {
                    "summary": "Completed the requested analysis",
                    "output": {"status": "done", "items": [1, 2, 3]},
                    "confidence": 0.92,
                    "followup_actions": ["review output"],
                }
            )
        )
