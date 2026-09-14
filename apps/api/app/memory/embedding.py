"""Embedding abstraction.

The rest of the memory system depends only on the :class:`EmbeddingProvider`
protocol — never on a concrete vendor. When no provider is configured the
system falls back to keyword matching for retrieval, so embeddings are an
optional enhancement rather than a hard requirement.

Providers produce deterministic vectors so semantic search is fully
exercisable without any external API key. ``MockEmbeddingProvider`` gives
lexically-grounded deterministic vectors; ``OpenAIEmbeddingProvider`` calls the
real embeddings API when a key is configured and falls back to a neutral vector
(keyless) otherwise.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


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
    """Real OpenAI embeddings provider.

    Calls the OpenAI ``/embeddings`` API over httpx (bounded timeout, retry +
    backoff via the shared :mod:`app.ai.providers._client`). When no API key is
    configured it silently falls back to a deterministic unit vector of the
    configured dimension, so the memory system keeps working keyless (semantic
    ranking simply degenerates to equal similarity, degrading gracefully to the
    keyword path).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        *,
        base_url: str = "",
        timeout: float | None = None,
        max_retries: int | None = None,
        retry_backoff: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._base_url = base_url
        self._transport = transport
        from app.core.config import settings  # deferred: avoid import cycle at module load

        self._timeout = timeout if timeout is not None else settings.openai_request_timeout_seconds
        self._max_retries = max_retries if max_retries is not None else settings.openai_max_retries
        self._retry_backoff = (
            retry_backoff if retry_backoff is not None else settings.openai_retry_backoff_seconds
        )

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        from app.ai.providers._client import (
            OpenAIRequestError,
            OpenAIUnavailableError,
            _request_async,
        )
        from app.core.config import settings

        base_url = self._base_url or settings.openai_base_url

        if not self._api_key:
            # Keyless fallback: stable unit vector with the configured dimension.
            vector = _normalize([1e-4] * self._dimensions)
            return [vector] * len(texts)

        try:
            data = await _request_async(
                method="POST",
                path="embeddings",
                base_url=base_url,
                api_key=self._api_key,
                json_body={"model": self._model, "input": texts},
                timeout=self._timeout,
                max_retries=self._max_retries,
                backoff=self._retry_backoff,
                transport=self._transport,
            )
        except (OpenAIRequestError, OpenAIUnavailableError):
            # Embeddings are a best-effort enhancement (retrieval falls back to
            # keyword matching); a failed vendor call must not break a run, but
            # the degradation should be visible in the logs, not silent.
            logger.warning("openai_embedding_degraded_to_neutral_vector")
            vector = _normalize([1e-4] * self._dimensions)
            return [vector] * len(texts)

        vectors: list[list[float]] = []
        for item in data.get("data") or []:
            vectors.append(_normalize(list(item.get("embedding", []))))
        # The API may return fewer vectors than inputs (empty inputs are
        # dropped); pad with the neutral vector to preserve ordering.
        while len(vectors) < len(texts):
            vectors.append(_normalize([1e-4] * self._dimensions))
        return vectors[: len(texts)]


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
        # The embeddings provider falls back to a neutral keyless vector when
        # no key is configured, so enabling the provider is always safe.
        return OpenAIEmbeddingProvider(
            api_key=getattr(settings, "openai_api_key", "") or "",
            model=settings.memory_embedding_model,
            base_url=getattr(settings, "openai_base_url", "") or "",
        )
    return None
