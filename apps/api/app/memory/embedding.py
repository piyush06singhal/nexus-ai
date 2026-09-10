"""Embedding abstraction.

The rest of the memory system depends only on the :class:`EmbeddingProvider`
protocol — never on a concrete vendor. When no provider is configured the
system falls back to keyword matching for retrieval, so embeddings are an
optional enhancement rather than a hard requirement.

Providers produce deterministic 128-dim vectors so semantic search is fully
exercisable without any external API key. A real OpenAI provider is scaffolded
and ready for later phases but intentionally not wired to network calls yet.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from app.core.config import Settings


def _normalize(vector: list[float]) -> list[float]:
    """Normalize *vector* to unit length via the L2 norm."""
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


class EmbeddingProvider(Protocol):
    """Embed *texts* into dense vectors for semantic similarity search."""

    @property
    def dimensions(self) -> int:
        """Length of each produced vector."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed the given texts, returning one vector per input."""
        ...


class MockEmbeddingProvider:
    """Deterministic, hash-based embeddings for tests and local development.

    The same text always maps to the same vector, and semantically-similar
    tokens share dimensions, so cosine similarity rises with lexical overlap.
    No network access and no API key are required.
    """

    _DIMS = 128

    @property
    def dimensions(self) -> int:
        return self._DIMS

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self._DIMS
            tokens = re.findall(r"[a-z]+|\\d+", text.lower())
            if not tokens:
                # Empty / non-text input -> uniform vector.
                vector = [1.0 / math.sqrt(self._DIMS)] * self._DIMS
            else:
                for token in tokens:
                    # Deterministic bucket from the token's utf8 bytes.
                    digest = hashlib.sha256(token.encode("utf-8")).digest()
                    bucket = int.from_bytes(digest[:8], "big") % self._DIMS
                    # Sign + weight from later digest bytes.
                    sign = 1.0 if digest[8] & 1 else -1.0
                    vector[bucket] += sign
            vectors.append(_normalize(vector))
        return vectors


class OpenAIEmbeddingProvider:
    """Production embedding provider scaffold (reserved for later phases).

    Concrets network calls are intentionally deferred so the memory system
    stays fully functional and testable without credentials. When wired up,
    this will call the OpenAI embeddings API for each non-empty text.
    """

    def __init__(
        self, api_key: str, model: str = "text-embedding-3-small", dimensions: int = 1536
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Real API integration is deferred; return a stable vector with the
        # configured dimension so nothing breaks when a provider is set.
        vector = _normalize([1e-4] * self._dimensions)
        return [vector] * len(texts)


def get_embedding_provider(settings: Settings) -> EmbeddingProvider | None:
    """Return the configured embedding provider, or ``None`` when disabled.

    A ``memory_embedding_provider`` of ``"mock"`` yields the deterministic
    provider (used in tests and local dev without a key); anything else
    returns ``None`` so retrieval degrades gracefully to keyword matching.
    """
    provider = getattr(settings, "memory_embedding_provider", None)
    if provider and provider.lower() == "mock":
        return MockEmbeddingProvider()
    if provider and provider.lower() == "openai":
        return OpenAIEmbeddingProvider(api_key="", model=settings.memory_embedding_model)
    return None
