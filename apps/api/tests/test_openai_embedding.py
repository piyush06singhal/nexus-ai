"""Tests for the real OpenAI embeddings provider (httpx.MockTransport based)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.memory.embedding import (
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    _normalize,
)

KEY = "sk-test-123"


def _embed_response(vectors: list[list[float]]) -> dict:
    return {
        "object": "list",
        "model": "text-embedding-3-small",
        "data": [
            {"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)
        ],
        "usage": {"prompt_tokens": 4, "total_tokens": 4},
    }


async def test_keyless_falls_back_to_neutral_vectors():
    provider = OpenAIEmbeddingProvider(api_key="", dimensions=1536)
    vectors = await provider.embed(["hello", "world"])
    assert len(vectors) == 2
    for v in vectors:
        assert len(v) == 1536
        assert abs(sum(x * x for x in v) - 1.0) < 1e-6  # unit length


async def test_real_call_posts_embeddings_payload():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_embed_response([[0.5, 0.5], [1.0, 0.0]]))

    provider = OpenAIEmbeddingProvider(
        api_key=KEY,
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
        max_retries=1,
    )
    vectors = await provider.embed(["alpha", "beta"])

    assert captured["url"] == "https://api.openai.com/v1/embeddings"
    assert captured["auth"] == f"Bearer {KEY}"
    assert captured["body"] == {"model": "text-embedding-3-small", "input": ["alpha", "beta"]}
    assert len(vectors) == 2
    assert abs(sum(x * x for x in vectors[0]) - 1.0) < 1e-6  # _normalize applied


async def test_api_failure_degrades_to_neutral_vectors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    provider = OpenAIEmbeddingProvider(
        api_key=KEY,
        transport=httpx.MockTransport(handler),
        max_retries=0,  # fail fast
        dimensions=8,
    )
    vectors = await provider.embed(["hello"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 8


async def test_shorter_response_pads_to_input_count():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_embed_response([[1.0, 0.0]]))

    provider = OpenAIEmbeddingProvider(
        api_key=KEY, transport=httpx.MockTransport(handler), dimensions=1536
    )
    vectors = await provider.embed(["a", "b", "c"])
    assert len(vectors) == 3
    assert vectors[1] == _normalize([1e-4] * 1536)  # padded with the neutral vector


async def test_mock_embedding_provider_is_deterministic():
    provider = MockEmbeddingProvider()
    a = await provider.embed(["semantic search"])
    b = await provider.embed(["semantic search"])
    assert a == b
    assert provider.dimensions == 128


@pytest.mark.live_api
async def test_live_embedding():
    """Real round-trip against api.openai.com (requires OPENAI_API_KEY).

    Deliberately rejects the constant neutral fallback vector: if the vendor
    call degraded (e.g. no credits), the response is indistinguishable from a
    stub, and *this* difference is exactly what a live test must catch.
    """
    import os

    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    provider = OpenAIEmbeddingProvider(api_key=key, max_retries=1)
    vectors = await provider.embed(["hello world live test"])
    assert len(vectors) == 1
    vector = vectors[0]
    assert len(vector) == provider.dimensions
    assert abs(sum(x * x for x in vector) - 1.0) < 1e-6
    # A genuine embedding is not a constant vector.
    distinct = sum(1 for x in vector if abs(x - vector[0]) > 1e-6)
    assert distinct > provider.dimensions // 2, "embedding looks like the neutral fallback"
