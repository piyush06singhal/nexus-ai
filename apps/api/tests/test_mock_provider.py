"""Tests for the MockProvider test double."""

from app.ai.providers.mock_provider import MockProvider
from app.ai.types import ChatMessage, TokenUsage


def test_mock_provider_generate_default():
    provider = MockProvider(reply='{"summary": "ok", "output": {"x": 1}}')
    response = provider.generate([ChatMessage(role="user", content="hi")])
    assert response.content == '{"summary": "ok", "output": {"x": 1}}'
    assert response.model == "mock-model"
    assert response.usage is not None
    assert response.usage.total_tokens == 15


def test_mock_provider_captures_messages_and_options():
    provider = MockProvider()
    provider.generate([ChatMessage(role="user", content="ping")], options=None)
    assert provider.last_messages is not None
    assert provider.last_messages[0].content == "ping"


def test_mock_provider_raises_configured_error():
    provider = MockProvider(reply="", raise_error=RuntimeError("boom"))
    try:
        provider.generate([])
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:  # pragma: no cover - defensive
        raise AssertionError("expected RuntimeError")


def test_mock_provider_stream_tokens():
    provider = MockProvider(reply='{"summary": "a b"}')
    parts = list(provider.stream([ChatMessage(role="user", content="hi")]))
    assert "".join(parts).strip() == '{"summary": "a b"}'


def test_mock_provider_json_preview_parses_as_agent_result():
    provider = MockProvider.json_preview()
    response = provider.generate([])
    from app.schemas.runtime import AgentResult

    result = AgentResult.model_validate_json(response.content)
    assert result.summary == "Completed the requested analysis"
    assert result.confidence == 0.92
    assert result.output["status"] == "done"


def test_mock_provider_usage_roundtrip():
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    provider = MockProvider(usage=usage)
    response = provider.generate([])
    assert response.usage == usage


def test_mock_provider_script_advances_then_repeats_last():
    """A scripted mock returns responses in order, then holds the last one.

    This models a model that requests a tool call, observes the result, and
    finally returns an AgentResult — the sequence a live tool-calling run uses.
    """
    provider = MockProvider(
        script=[
            '{"tool_calls": [{"tool": "calculator", "arguments": {"expression": "2+3"}}]}',
            '{"summary": "done", "output": {"result": 5}}',
        ]
    )
    assert provider.generate([]).content.startswith('{"tool_calls"')
    assert provider.generate([]).content.startswith('{"summary"')
    # Holds the last scripted response on further calls.
    assert provider.generate([]).content.startswith('{"summary"')


def test_mock_provider_script_falls_back_to_empty_list():
    provider = MockProvider(script=[])
    assert provider.generate([]).content == '{"summary": "ok", "output": {}}'
