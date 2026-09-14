"""Anthropic (Claude) provider adapter.

Implements ``BaseModelProvider`` against the Anthropic Messages API
(``POST /v1/messages``) with the same safety contract as the OpenAI adapter:

- ``stub_enabled=True`` (tests / explicit opt-in): deterministic canned output
  prefixed ``[stub:anthropic]``.
- No API key configured (a stranger's fresh checkout): silent deterministic
  fallback using the same canned output.

With a key, the adapter makes the real call over the shared
:mod:`app.ai.providers._client` transport — same bounded timeouts,
exponential-backoff retries and error mapping — passing the headers Anthropic
requires (``x-api-key`` + ``anthropic-version``). Usage (``input_tokens`` /
``output_tokens``) is normalized into ``TokenUsage`` and recorded into the
process metrics registry, matching the OpenAI adapter.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

from app.ai.base import BaseModelProvider
from app.ai.providers._client import (
    ANTHROPIC_BASE_URL,
    OpenAIRequestError,
    OpenAIUnavailableError,
    _request,
    _stream,
)
from app.ai.types import ChatMessage, GenerationOptions, ModelResponse, TokenUsage
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import model_tokens

logger = get_logger(__name__)

_MESSAGES_PATH = "messages"
_ANTHROPIC_VERSION = "2023-06-01"

#: ``stop_reason`` -> normalized ``finish_reason`` (matches OpenAI vocabulary
#: so downstream callers see consistent values regardless of vendor).
_FINISH_REASON_MAP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


class AnthropicProvider(BaseModelProvider):
    """Anthropic Messages-API provider.

    Args:
        stub_enabled: If True, return deterministic canned output (tests).
        api_key / base_url / model / timeout / max_retries / backoff: explicit
            overrides; default to the corresponding ``settings`` values so a
            registry-constructed instance (``get_provider("anthropic")``) picks
            up the environment automatically.
        transport: httpx transport seam for tests (``httpx.MockTransport``);
            None means the real network client.
    """

    name = "anthropic"
    default_model = "claude-sonnet-5"

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
        self.api_key = api_key if api_key is not None else settings.anthropic_api_key
        self.base_url = base_url if base_url is not None else settings.anthropic_base_url
        self.timeout = (
            timeout if timeout is not None else settings.anthropic_request_timeout_seconds
        )
        self.max_retries = (
            max_retries if max_retries is not None else settings.anthropic_max_retries
        )
        self.retry_backoff = (
            retry_backoff if retry_backoff is not None else settings.anthropic_retry_backoff_seconds
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

        payload = self._build_payload(messages, options, model)
        started = time.perf_counter()
        try:
            data = _request(
                method="POST",
                path=_MESSAGES_PATH,
                base_url=self.base_url,
                api_key=self.api_key,
                json_body=payload,
                timeout=self.timeout,
                max_retries=self.max_retries,
                backoff=self.retry_backoff,
                # Anthropic authenticates via x-api-key, not Authorization: Bearer.
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": _ANTHROPIC_VERSION,
                },
                default_base_url=ANTHROPIC_BASE_URL,
                transport=self._transport,
            )
        except (OpenAIRequestError, OpenAIUnavailableError):
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0

        response = self._parse(data, options, latency_ms)
        logger.info(
            "anthropic.completion",
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
        """Native Anthropic SSE streaming of ``content_block_delta`` text.

        Requests ``stream: true``; token deltas are yielded as they arrive and
        the accumulated text, ``stop_reason`` and input/output token counts (from
        the ``message_start`` / ``message_delta`` frames) are recorded for the
        completion log and metrics registry. Keyless/stub mode degrades to the
        deterministic canned text.
        """
        model = self._resolve_model(options)

        if self.stub_enabled or not self.api_key:
            if self.stub_enabled:
                self._log_fallback("stub_enabled")
            else:
                self._log_fallback("no_api_key")
            response = self._fallback(messages, model)
            for token in response.content.split(" "):
                yield token + " "
            return

        payload = self._build_payload(messages, options, model)
        payload["stream"] = True

        started = time.perf_counter()
        try:
            frames = _stream(
                method="POST",
                path=_MESSAGES_PATH,
                base_url=self.base_url,
                api_key=self.api_key,
                json_body=payload,
                timeout=self.timeout,
                max_retries=self.max_retries,
                backoff=self.retry_backoff,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": _ANTHROPIC_VERSION,
                },
                default_base_url=ANTHROPIC_BASE_URL,
                transport=self._transport,
            )
        except (OpenAIRequestError, OpenAIUnavailableError):
            raise

        full_text: list[str] = []
        finish_reason = "stop"
        input_tokens = 0
        output_tokens = 0
        for frame in frames:
            frame_type = frame.get("type")
            if frame_type == "content_block_delta":
                token = (frame.get("delta") or {}).get("text")
                if token:
                    full_text.append(token)
                    yield token
            elif frame_type == "message_start":
                usage = (frame.get("message") or {}).get("usage") or {}
                input_tokens = int(usage.get("input_tokens") or 0)
            elif frame_type == "message_delta":
                stop_reason = (frame.get("delta") or {}).get("stop_reason")
                if stop_reason:
                    finish_reason = _FINISH_REASON_MAP.get(stop_reason, stop_reason)
                usage = frame.get("usage") or {}
                output_tokens = int(usage.get("output_tokens") or 0)

        latency_ms = (time.perf_counter() - started) * 1000.0
        token_usage = None
        if input_tokens or output_tokens:
            token_usage = TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )
            model_tokens(model, input_tokens, output_tokens)
        logger.info(
            "anthropic.stream",
            extra={
                "model": model,
                "finish_reason": finish_reason,
                "latency_ms": round(latency_ms, 1),
                "tokens": token_usage.total_tokens if token_usage else len("".join(full_text)),
            },
        )

    # ── request construction ───────────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[ChatMessage],
        options: GenerationOptions | None,
        model: str,
    ) -> dict[str, Any]:
        """Build an Anthropic ``/v1/messages`` body.

        The Messages API has no ``system`` role in ``messages`` — system
        instructions are a top-level ``system`` field, so they are hoisted out.
        ``max_tokens`` is mandatory for Anthropic and always set.
        """
        system_parts: list[str] = []
        api_messages: list[dict[str, str]] = []
        for message in messages:
            if message.role == "system":
                system_parts.append(message.content)
            else:
                api_messages.append({"role": message.role, "content": message.content})

        payload: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": (
                options.max_tokens
                if options is not None and options.max_tokens is not None
                else self.default_max_tokens
            ),
            "temperature": (
                options.temperature
                if options is not None and options.temperature is not None
                else self.default_temperature
            ),
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)
        if options is not None:
            if options.top_p is not None:
                payload["top_p"] = options.top_p
            if options.stop:
                payload["stop_sequences"] = options.stop
        return payload

    # ── response parsing ───────────────────────────────────────────────────

    def _parse(
        self, data: dict, options: GenerationOptions | None, latency_ms: float
    ) -> ModelResponse:
        content_blocks = data.get("content")
        if not isinstance(content_blocks, list):
            raise OpenAIUnavailableError("Anthropic response missing content")

        text = "".join(
            block.get("text") or ""
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        model = data.get("model") or self._resolve_model(options)
        stop_reason = data.get("stop_reason") or "end_turn"
        finish_reason = _FINISH_REASON_MAP.get(stop_reason, stop_reason)

        usage = data.get("usage")
        token_usage = None
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("input_tokens") or 0)
            completion_tokens = int(usage.get("output_tokens") or 0)
            token_usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            model_tokens(model, prompt_tokens, completion_tokens)

        return ModelResponse(
            content=text,
            model=model,
            finish_reason=finish_reason,
            usage=token_usage,
            latency_ms=latency_ms,
        )

    # ── fallback ───────────────────────────────────────────────────────────

    def _fallback(self, messages: list[ChatMessage], model: str) -> ModelResponse:
        prompt = messages[-1].content if messages else ""
        return ModelResponse(
            content=(f"[stub:anthropic] Received {len(messages)} message(s). Last: {prompt[-60:]}"),
            model=model,
            finish_reason="stop",
        )

    @staticmethod
    def _log_fallback(reason: str) -> None:
        logger.debug("anthropic.fallback", extra={"reason": reason})
