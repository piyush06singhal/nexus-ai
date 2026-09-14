"""Real OpenAI-compatible model provider.

Replaces the Phase 0 stub with a genuine client for the OpenAI Chat
Completions API (and any OpenAI-compatible endpoint via
``openai_base_url``), while preserving two safe fallback behaviours so the
platform never silently breaks:

- ``stub_enabled=True`` (tests / explicit opt-in): deterministic canned output
  prefixed ``[stub:openai]`` as before.
- No API key configured (a stranger's fresh checkout): silent deterministic
  fallback using the same canned output. A key is only *required* to get real
  model intelligence; without one the rest of the platform runs unchanged.

With a key, ``generate``/``stream`` make the real API call (bounded timeout,
exponential-backoff retries on transient failures), parse usage into
``ModelResponse``, and record token metrics into the process registry
(``app.core.metrics.model_tokens``).

Native OpenAI ``tool_calls`` (when the API returns them) are mapped into the
runtime's JSON ``{"tool_calls": [...]}`` shape so the tool loop can consume
them.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import httpx

from app.ai.base import BaseModelProvider
from app.ai.providers._client import (
    OpenAIRequestError,
    OpenAIUnavailableError,
    _request,
)
from app.ai.types import ChatMessage, GenerationOptions, ModelResponse, TokenUsage
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import model_tokens

logger = get_logger(__name__)

_CHAT_PATH = "chat/completions"


class OpenAIProvider(BaseModelProvider):
    """OpenAI-compatible chat-completions provider.

    Args:
        stub_enabled: If True, return deterministic canned output (tests).
        api_key / base_url / model / timeout / max_retries / backoff: explicit
            overrides; default to the corresponding ``settings`` values so a
            registry-constructed instance (``get_provider("openai")``) picks up
            the environment automatically.
        transport: httpx transport seam for tests (``httpx.MockTransport``);
            None means the real network client.
    """

    name = "openai"
    default_model = "gpt-4o-mini"

    def __init__(
        self,
        *,
        stub_enabled: bool = False,
        default_model: str | None = None,
        default_temperature: float | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        retry_backoff: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(default_model=default_model, default_temperature=default_temperature)
        self.stub_enabled = stub_enabled
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.base_url = base_url if base_url is not None else settings.openai_base_url
        self.timeout = timeout if timeout is not None else settings.openai_request_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.openai_max_retries
        self.retry_backoff = (
            retry_backoff if retry_backoff is not None else settings.openai_retry_backoff_seconds
        )
        self._transport = transport

    # ── public contract ────────────────────────────────────────────────────

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        options: GenerationOptions | None = None,
    ) -> ModelResponse:
        model = self._resolve_model(options)

        if self.stub_enabled or not self.api_key:
            if self.stub_enabled:
                self._log_fallback("stub_enabled")
            else:
                self._log_fallback("no_api_key")
            return self._fallback(messages, model)

        payload = self._build_payload(messages, options)
        started = time.perf_counter()
        try:
            data = _request(
                method="POST",
                path=_CHAT_PATH,
                base_url=self.base_url,
                api_key=self.api_key,
                json_body=payload,
                timeout=self.timeout,
                max_retries=self.max_retries,
                backoff=self.retry_backoff,
                transport=self._transport,
            )
        except (OpenAIRequestError, OpenAIUnavailableError):
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0

        response = self._parse(data, options, latency_ms)
        logger.info(
            "openai.completion",
            extra={
                "model": response.model,
                "finish_reason": response.finish_reason,
                "latency_ms": round(latency_ms, 1),
                "tokens": response.usage.total_tokens if response.usage else 0,
            },
        )
        return response

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        # Real streaming (SSE token deltas) is intentionally not implemented;
        # the runtime consumes ``generate`` and splits tokens itself. Keep the
        # contract: ``stream`` yields the same content in whitespace tokens.
        response = self.generate(messages, options=options)
        for token in response.content.split(" "):
            yield token + " "

    # ── request construction ───────────────────────────────────────────────

    def _build_payload(
        self, messages: list[ChatMessage], options: GenerationOptions | None
    ) -> dict:
        payload: dict = {
            "model": self._resolve_model(options),
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                    # tool-call results must be attachable to the message
                    **({"name": message.name} if message.name else {}),
                }
                for message in messages
            ],
            "temperature": (
                options.temperature
                if options is not None and options.temperature is not None
                else self.default_temperature
            ),
            "max_tokens": (
                options.max_tokens
                if options is not None and options.max_tokens is not None
                else self.default_max_tokens
            ),
        }
        if options is not None:
            if options.top_p is not None:
                payload["top_p"] = options.top_p
            if options.stop:
                payload["stop"] = options.stop
        return payload

    # ── response parsing ───────────────────────────────────────────────────

    def _parse(
        self, data: dict, options: GenerationOptions | None, latency_ms: float
    ) -> ModelResponse:
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError) as exc:
            raise OpenAIUnavailableError(f"OpenAI response missing choices: {exc!r}") from exc

        model = data.get("model") or self._resolve_model(options)
        content = (choice.get("message") or {}).get("content") or ""

        # Native tool calls -> runtime JSON shape (best-effort, guarded).
        tool_calls = (choice.get("message") or {}).get("tool_calls")
        if tool_calls:
            mapped = self._map_tool_calls(tool_calls)
            if content and content.strip():
                wrapped = {"tool_calls": mapped, "text": content}
            else:
                wrapped = {"tool_calls": mapped}
            content = json.dumps(wrapped)

        finish_reason = choice.get("finish_reason") or "stop"
        usage = data.get("usage")
        token_usage = None
        if usage:
            token_usage = TokenUsage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            )
            model_tokens(model, token_usage.prompt_tokens, token_usage.completion_tokens)

        return ModelResponse(
            content=content,
            model=model,
            finish_reason=finish_reason,
            usage=token_usage,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _map_tool_calls(tool_calls: list[dict]) -> list[dict]:
        """Map OpenAI native ``tool_calls`` to the runtime's tool shape.

        The runtime expects ``{"tool_calls": [{"tool": str, "arguments": dict}]}``.
        Parsing failures for a single entry are tolerated (the entry is skipped)
        so one malformed tool call cannot break the whole response.
        """
        mapped: list[dict] = []
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name")
            if not name or not name.strip():
                continue
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            mapped.append({"tool": name, "arguments": arguments})
        return mapped

    # ── fallback ───────────────────────────────────────────────────────────

    def _fallback(self, messages: list[ChatMessage], model: str) -> ModelResponse:
        prompt = messages[-1].content if messages else ""
        return ModelResponse(
            content=f"[stub:openai] Received {len(messages)} message(s). Last: {prompt[-60:]}",
            model=model,
            finish_reason="stop",
        )

    @staticmethod
    def _log_fallback(reason: str) -> None:
        logger.debug("openai.fallback", extra={"reason": reason})
