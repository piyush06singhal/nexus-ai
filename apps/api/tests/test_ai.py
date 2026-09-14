"""Tests for the AI abstraction layer."""

import pytest

from app.ai import get_provider, list_providers, register_provider
from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.types import ChatMessage, GenerationOptions


def test_list_providers_contains_openai():
    providers = list_providers()
    assert "openai" in providers


def test_get_provider_resolves_openai():
    provider = get_provider("openai")
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"


def test_get_provider_unknown_raises():
    with pytest.raises(KeyError):
        get_provider("does-not-exist")


def test_register_provider():
    class DummyProvider(OpenAIProvider):
        name = "dummy"

    register_provider("dummy", DummyProvider)
    try:
        assert "dummy" in list_providers()
        assert isinstance(get_provider("dummy"), DummyProvider)
    finally:
        # Clean up so other tests stay isolated.
        from app.ai import registry as _reg

        _reg._PROVIDER_FACTORIES.pop("dummy", None)


def test_stub_provider_generate_requires_flag():
    # Without a key the provider degrades to a deterministic fallback rather
    # than raising — a stranger's checkout must never break on a missing key.
    provider = get_provider("openai")
    response = provider.generate([ChatMessage(role="user", content="hello")])
    assert response.content.startswith("[stub:openai]")


def test_stub_provider_canned_output():
    provider = OpenAIProvider(stub_enabled=True)
    messages = [ChatMessage(role="user", content="ping")]
    response = provider.generate(messages, options=GenerationOptions(model="gpt-4o-mini"))
    assert "[stub:openai]" in response.content
    assert response.model == "gpt-4o-mini"


def test_stub_provider_stream():
    provider = OpenAIProvider(stub_enabled=True)
    parts = list(provider.stream([ChatMessage(role="user", content="ping")]))
    assert parts
    assert isinstance(parts[0], str)
