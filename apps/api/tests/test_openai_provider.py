"""Tests for the real OpenAI chat-completions provider.

All network calls are intercepted with ``httpx.MockTransport`` so the suite
runs keyless in CI. A live round-trip is covered by ``live_api``-marked tests
that auto-skip when ``OPENAI_API_KEY`` is not set (see the `.env` only on the
author's machine).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.providers._client import OpenAIRequestError, OpenAIUnavailableError
from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.types import ChatMessage, GenerationOptions

KEY = "sk-test-123"
MESSAGES = [
    ChatMessage(role="system", content="you are terse"),
    ChatMessage(role="user", content="hello"),
]


def _chat_response(content: str = "hello back") -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _chat_completion_chunk(text: str, *, finish_reason: str = "stop") -> dict:
    """One OpenAI chat.completion.chunk frame (token content or a finish)."""
    return {
        "id": "chatcmpl-s1",
        "object": "chat.completion.chunk",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "delta": {"content": text} if text else {},
                "finish_reason": finish_reason if not text else None,
            }
        ],
    }


def _sse_stream(text: str, *, finish_reason: str = "stop", with_usage: bool = True) -> str:
    """Build an OpenAI streaming ``text/event-stream`` body.

    The text is split into deterministic 3-char deltas so the test can assert
    that tokens arrive in order and piece back together exactly.
    """
    frames = []
    for i in range(0, len(text), 3):
        chunk = text[i : i + 3]
        frames.append("data: " + json.dumps(_chat_completion_chunk(chunk)) + "\n")
    frames.append(
        "data: " + json.dumps(_chat_completion_chunk("", finish_reason=finish_reason)) + "\n"
    )
    if with_usage:
        frames.append(
            "data: "
            + json.dumps(
                {
                    "id": "chatcmpl-s1",
                    "object": "chat.completion.chunk",
                    "model": "gpt-4o-mini",
                    "choices": [],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                }
            )
            + "\n"
        )
    frames.append("data: [DONE]\n\n")
    return "".join(frames)


def test_keyless_fallback_is_deterministic():
    provider = OpenAIProvider(api_key="")
    r1 = provider.generate(MESSAGES)
    r2 = provider.generate(MESSAGES)
    assert r1.content.startswith("[stub:openai]")
    assert r1.content == r2.content
    assert r1.model == "gpt-4o-mini"


def test_generate_real_call_parses_response():
    captured: dict = {}
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_chat_response("genuine reply"))

    provider = OpenAIProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2)
    response = provider.generate(
        MESSAGES,
        options=GenerationOptions(model="gpt-4o", temperature=0.3, max_tokens=500),
    )

    assert response.content == "genuine reply"
    assert response.model == "gpt-4o-mini"
    assert response.finish_reason == "stop"
    assert response.usage is not None and response.usage.total_tokens == 15
    assert response.latency_ms is not None and response.latency_ms >= 0

    # Exact request contract.
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["authorization"] == f"Bearer {KEY}"  # httpx lowercases header keys
    assert captured["headers"]["content-type"] == "application/json"
    body = captured["body"]
    assert body["model"] == "gpt-4o"
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 500
    assert body["messages"] == [
        {"role": "system", "content": "you are terse"},
        {"role": "user", "content": "hello"},
    ]
    assert len(calls) == 1  # no retries on success


def test_generate_retries_on_429_then_succeeds():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(200, json=_chat_response("recovered"))

    provider = OpenAIProvider(
        api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2, retry_backoff=0.0
    )
    response = provider.generate(MESSAGES)
    assert response.content == "recovered"
    assert len(attempts) == 2


def test_generate_retries_exhausted_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "busy"}})

    provider = OpenAIProvider(
        api_key=KEY, transport=httpx.MockTransport(handler), max_retries=1, retry_backoff=0.0
    )
    with pytest.raises(OpenAIUnavailableError):
        provider.generate(MESSAGES)


def test_generate_4xx_raises_request_error_no_retry():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(400, json={"error": {"message": "bad model"}})

    provider = OpenAIProvider(
        api_key=KEY, transport=httpx.MockTransport(handler), max_retries=3, retry_backoff=0.0
    )
    with pytest.raises(OpenAIRequestError) as exc:
        provider.generate(MESSAGES)
    assert exc.value.status == 400
    assert len(attempts) == 1


def test_stream_contract():
    """Native SSE streaming: tokens arrive in order and reassemble exactly."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_sse_stream("two words"),
            headers={"content-type": "text/event-stream"},
        )

    provider = OpenAIProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2)
    parts = list(provider.stream(MESSAGES))
    assert "".join(parts) == "two words"


def test_stream_requests_native_streaming():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            text=_sse_stream("hello back"),
            headers={"content-type": "text/event-stream"},
        )

    provider = OpenAIProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2)
    assert "".join(provider.stream(MESSAGES)) == "hello back"
    assert captured["body"]["stream"] is True
    assert captured["body"]["stream_options"] == {"include_usage": True}


def test_stream_accumulates_usage(monkeypatch):
    recorded: list[tuple] = []
    import app.ai.providers.openai_provider as provider_mod

    monkeypatch.setattr(
        provider_mod,
        "model_tokens",
        lambda model, prompt, complet: recorded.append((model, prompt, complet)),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_sse_stream("hi there"),
            headers={"content-type": "text/event-stream"},
        )

    provider = OpenAIProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2)
    assert "".join(provider.stream(MESSAGES)) == "hi there"
    # Usage frame arrives after the finish_reason chunk; prompt/completion are
    # recorded into the metrics registry.
    assert recorded == [("gpt-4o-mini", 10, 5)]


def test_stream_retries_429_then_streams():
    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(
            200,
            text=_sse_stream("recovered"),
            headers={"content-type": "text/event-stream"},
        )

    provider = OpenAIProvider(
        api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2, retry_backoff=0.0
    )
    assert "".join(provider.stream(MESSAGES)) == "recovered"
    assert len(attempts) == 2  # connect-time retry still applies


def test_stream_4xx_raises_request_error_no_retry():
    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    provider = OpenAIProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2)
    with pytest.raises(OpenAIRequestError) as exc_info:
        list(provider.stream(MESSAGES))
    assert exc_info.value.status == 400
    assert len(attempts) == 1


def test_stream_keyless_fallback_yields_canned_text():
    provider = OpenAIProvider(api_key="")
    parts = list(provider.stream(MESSAGES))
    assert "".join(parts).strip().startswith("[stub:openai]")


def test_native_tool_calls_map_to_runtime_shape():
    payload = {
        "id": "chatcmpl-2",
        "object": "chat.completion",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "calculator", "arguments": '{"a": 1, "b": 2}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = OpenAIProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=1)
    response = provider.generate(MESSAGES)
    parsed = json.loads(response.content)
    assert parsed["tool_calls"] == [{"tool": "calculator", "arguments": {"a": 1, "b": 2}}]
    assert response.usage.total_tokens == 7


def test_malformed_tool_call_is_skipped():
    payload = {
        "id": "chatcmpl-3",
        "object": "chat.completion",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "{}",
                    "tool_calls": [
                        {
                            "id": "call_bad",
                            "type": "function",
                            "function": {"name": "calculator", "arguments": "not-json"},
                        }
                    ],
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = OpenAIProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=1)
    response = provider.generate(MESSAGES)
    parsed = json.loads(response.content)
    # Malformed arguments fall back to {} so the tool still executes; the
    # caller-side validation is what flags bad data.
    assert parsed["tool_calls"] == [{"tool": "calculator", "arguments": {}}]


def test_custom_base_url_is_used():
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=_chat_response())

    provider = OpenAIProvider(
        api_key=KEY,
        base_url="http://localhost:9999/v1",
        transport=httpx.MockTransport(handler),
    )
    provider.generate(MESSAGES)
    assert seen_urls == ["http://localhost:9999/v1/chat/completions"]


def _structured_schema():
    """A fully-defaulted Pydantic schema for structured-output tests."""
    from pydantic import BaseModel

    class PlayerSchema(BaseModel):
        name: str = ""
        score: int = 0

    return PlayerSchema


def test_structured_output_sends_native_json_schema_mode():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_chat_response('{"name": "ada", "score": 7}'))

    provider = OpenAIProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=2)
    Schema = _structured_schema()
    result = provider.structured_output(MESSAGES, schema=Schema)

    # Native json_schema mode enforced by the API, then validated.
    assert result.name == "ada"
    assert result.score == 7
    fmt = captured["body"]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "PlayerSchema"
    assert fmt["json_schema"]["strict"] is False
    assert fmt["json_schema"]["schema"] == Schema.model_json_schema()


def test_structured_output_keyless_returns_validated_default_instance():
    provider = OpenAIProvider(api_key="")
    result = provider.structured_output(MESSAGES, schema=_structured_schema())
    # Offline deterministic contract: a validated default instance.
    assert result.name == ""
    assert result.score == 0


def test_structured_output_degrades_when_json_schema_rejected():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format unsupported"}})
        return httpx.Response(200, json=_chat_response('{"name": "grace", "score": 3}'))

    provider = OpenAIProvider(
        api_key=KEY, transport=httpx.MockTransport(handler), max_retries=1, retry_backoff=0.0
    )
    result = provider.structured_output(MESSAGES, schema=_structured_schema())
    assert result.name == "grace"
    assert result.score == 3
    # Native attempt rejected the json_schema param; the base path re-issued
    # without response_format (4xx is not retried, so exactly two requests).
    assert len(bodies) == 2
    assert "response_format" in bodies[0]
    assert "response_format" not in bodies[1]


def test_structured_output_invalid_response_propagates_validation_error():
    from pydantic import ValidationError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response('{"name": 42}'))  # name not a str

    provider = OpenAIProvider(api_key=KEY, transport=httpx.MockTransport(handler), max_retries=1)
    with pytest.raises(ValidationError):
        provider.structured_output(MESSAGES, schema=_structured_schema())


@pytest.mark.live_api
def test_live_chat_completion():
    key = _live_key()
    if key is None:
        pytest.skip("OPENAI_API_KEY not set")
    response = OpenAIProvider(api_key=key, max_retries=1).generate(
        [ChatMessage(role="user", content="Reply with exactly: OK")]
    )
    assert response.content.strip().upper() == "OK"
    assert response.usage is not None and response.usage.total_tokens > 0
    assert response.latency_ms is not None


def _live_key() -> str | None:
    import os

    key = os.environ.get("OPENAI_API_KEY", "").strip()
    return key or None
