"""Tests for the embedding provider abstraction (Phase 4)."""

import asyncio

from app.core.config import Settings
from app.memory.embedding import (
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)


def test_mock_embedding_dimensions():
    provider = MockEmbeddingProvider()
    assert provider.dimensions == 128


def test_mock_embedding_deterministic():
    provider = MockEmbeddingProvider()
    (a,) = asyncio.run(provider.embed(["hello world"]))
    (b,) = asyncio.run(provider.embed(["hello world"]))
    assert a == b


def test_mock_embedding_unit_length():
    provider = MockEmbeddingProvider()
    (v,) = asyncio.run(provider.embed(["alpha beta gamma"]))
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_mock_embedding_distinguishes_different_texts():
    provider = MockEmbeddingProvider()
    (a,) = asyncio.run(provider.embed(["sales report" * 5]))
    (b,) = asyncio.run(provider.embed(["cooking pasta" * 5]))
    assert a != b


def test_mock_embedding_empty_text_nonzero():
    provider = MockEmbeddingProvider()
    (v,) = asyncio.run(provider.embed([""]))
    assert any(x != 0 for x in v)


def test_openai_provider_scaffold():
    provider = OpenAIEmbeddingProvider(api_key="test")
    assert provider.dimensions == 1536


def test_get_provider_none_by_default():
    settings = Settings(memory_embedding_provider=None, _env_file=None)
    assert get_embedding_provider(settings) is None


def test_get_provider_mock():
    settings = Settings(memory_embedding_provider="mock", _env_file=None)
    provider = get_embedding_provider(settings)
    assert isinstance(provider, MockEmbeddingProvider)


def test_get_provider_openai():
    settings = Settings(memory_embedding_provider="openai", _env_file=None)
    provider = get_embedding_provider(settings)
    assert isinstance(provider, OpenAIEmbeddingProvider)
