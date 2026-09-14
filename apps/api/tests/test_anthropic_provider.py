"""Tests for the Anthropic (Claude) Messages-API provider.

All network calls are intercepted with ``httpx.MockTransport`` so the suite
runs keyless in CI. A live round-trip is covered by a ``live_api``-marked test
that auto-skips when ``ANTHROPIC_API_KEY`` is not set (see the `.env` only on
the author's machine).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.providers._client import OpenAIRequestError, OpenAIUnavailableError
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.types import ChatMessage, GenerationOptions

KEY = "sk-ant-test-123"
MESSAGES = [
    ChatMessage(role="system", content="you are terse"),
    ChatMessage(role="user", content="hello"),
]


def _messages_response(text: str = "hello back") -> dict:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def test_keyless_fallback_is_deterministic():
    provider = AnthropicProvider(api_key="")
    r1 = provider.generate(MESSAGES)
    r2 = provider.generate(MESSAGES)
    assert r1.content.startswith("[stub:anthropic]")
    assert r1.content == r2.content
    assert r1.model == "claude-sonnet-5"


def test_generate_parses_messages_response():
    captured: dict = {}
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_messages_response("genuine reply"))

    provider = AnthropicProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2)
    response = provider.generate(
        MESSAGES,
        options=GenerationOptions(model="claude-opus-5", temperature=0.2, max_tokens=800),
    )

    assert response.content == "genuine reply"
    assert response.model == "claude-sonnet-5"  # normalized from the response
    assert response.finish_reason == "stop"  # end_turn -> stop
    assert response.usage is not None
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 5
    assert response.usage.total_tokens == 15
    assert response.latency_ms is not None and response.latency_ms >= 0

    # Exact request contract (Anthropic Messages API).
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == KEY
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["headers"]["content-type"] == "application/json"
    body = captured["body"]
    assert body["model"] == "claude-opus-5"
    assert body["max_tokens"] == 800
    assert body["temperature"] == 0.2
    # System role hoisted to the top-level "system" field.
    assert body["system"] == "you are terse"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert len(calls) == 1


def test_generate_uses_defaults_when_no_overrides():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_messages_response())

    provider = AnthropicProvider(api_key=KEY, transport=httpx.MockTransport(handler))
    provider.generate([ChatMessage(role="user", content="hi")])

    # max_tokens is mandatory for Anthropic and always set even without options.
    assert captured["body"]["max_tokens"] == 4096
    assert captured["body"]["model"] == "claude-sonnet-5"
    assert "system" not in captured["body"]
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]


def test_generate_maps_stop_reasons():
    provider = AnthropicProvider(api_key="")
    for stop_reason, expected in (
        ("end_turn", "stop"),
        ("stop_sequence", "stop"),
        ("max_tokens", "length"),
        ("tool_use", "tool_calls"),
        ("unexpected_reason", "unexpected_reason"),  # unknown reasons pass through
    ):
        parsed = provider._parse({**_messages_response(), "stop_reason": stop_reason}, None, 1.0)
        assert parsed.finish_reason == expected


def _sse_anthropic(text: str, *, stop_reason: str = "end_turn") -> str:
    """Build an Anthropic streaming SSE body with named events."""
    frames = [
        "event: message_start\n"
        'data: {"type":"message_start","message":{"model":"claude-sonnet-5",'
        '"usage":{"input_tokens":10}}}\n\n',
    ]
    for i in range(0, len(text), 3):
        chunk = text[i : i + 3]
        frames.append(
            "event: content_block_delta\n"
            f'data: {{"type":"content_block_delta","index":0,'
            f'"delta":{{"type":"text_delta","text":"{chunk}"}}}}\n\n'
        )
    frames.append(
        "event: message_delta\n"
        f'data: {{"type":"message_delta","delta":{{"stop_reason":"{stop_reason}"}},'
        '"usage":{"output_tokens":5}}\n\n'
    )
    frames.append('event: message_stop\ndata: {"type":"message_stop"}\n\n')
    return "".join(frames)


def test_stream_yields_in_order_with_usage(monkeypatch):
    recorded: list[tuple] = []
    import app.ai.providers.anthropic_provider as provider_mod

    monkeypatch.setattr(
        provider_mod,
        "model_tokens",
        lambda model, prompt, complet: recorded.append((model, prompt, complet)),
    )

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            text=_sse_anthropic("hello back"),
            headers={"content-type": "text/event-stream"},
        )

    provider = AnthropicProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2)
    parts = list(provider.stream(MESSAGES))
    assert "".join(parts) == "hello back"
    assert captured["body"]["stream"] is True
    assert recorded == [("claude-sonnet-5", 10, 5)]


def test_stream_keyless_fallback_yields_canned_text():
    provider = AnthropicProvider(api_key="")
    assert "".join(list(provider.stream(MESSAGES))).strip().startswith("[stub:anthropic]")


def test_generate_retries_on_429_then_succeeds():
    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(200, json=_messages_response("recovered"))

    provider = AnthropicProvider(
        api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2, retry_backoff=0.0
    )
    response = provider.generate(MESSAGES)
    assert response.content == "recovered"
    assert len(attempts) == 2


def test_generate_4xx_raises_request_error_no_retry():
    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(401, json={"error": {"type": "authentication_error"}})

    provider = AnthropicProvider(
        api_key=KEY, transport=httpx.MockTransport(handler), max_retries=3, retry_backoff=0.0
    )
    with pytest.raises(OpenAIRequestError) as exc:
        provider.generate(MESSAGES)
    assert exc.value.status == 401
    assert len(attempts) == 1


def test_generate_retries_exhausted_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "overloaded"}})

    provider = AnthropicProvider(
        api_key=KEY, transport=httpx.MockTransport(handler), max_retries=1, retry_backoff=0.0
    )
    with pytest.raises(OpenAIUnavailableError):
        provider.generate(MESSAGES)


def test_structured_output_keyless_returns_validated_default_instance():
    from pydantic import BaseModel

    class PlayerSchema(BaseModel):
        name: str = ""
        score: int = 0

    provider = AnthropicProvider(api_key="")
    result = provider.structured_output(MESSAGES, schema=PlayerSchema)
    assert result.name == ""
    assert result.score == 0


def test_structured_output_with_key_delegates_to_base_json_path():
    from pydantic import BaseModel

    class PlayerSchema(BaseModel):
        name: str = ""
        score: int = 0

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_messages_response('{"name": "claude", "score": 9}'))

    provider = AnthropicProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2)
    result = provider.structured_output(MESSAGES, schema=PlayerSchema)
    assert result.name == "claude"
    assert result.score == 9


def test_missing_content_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "msg_1", "model": "claude-sonnet-5"})

    provider = AnthropicProvider(api_key=KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(OpenAIUnavailableError):
        provider.generate(MESSAGES)


@pytest.mark.live_api
def test_live_generate():
    """Real Anthropic round-trip; requires ANTHROPIC_API_KEY in the env."""
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    provider = AnthropicProvider()
    response = provider.generate([ChatMessage(role="user", content="say 'pong'")])
    assert response.content.strip()
    assert response.usage is not None and response.usage.total_tokens > 0
