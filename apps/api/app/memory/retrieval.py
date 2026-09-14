"""Hybrid memory retrieval.

Combines semantic similarity (when an embedding provider is present), lexical
keyword matching, recency decay, and importance/confidence weighting into a
single ranked list. Each signal contributes to a weighted final score, and the
result carries a ``breakdown`` so callers can see *why* a memory scored how it
did — matching the observability principle used across the codebase.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.memory import Memory, MemoryStatus, MemoryType
from app.memory.embedding import EmbeddingProvider
from app.memory.pgvector import (
    nearest_neighbours_clause,
    pgvector_enabled,
    vector_literal,
)
from app.memory.policies import RetrievalPolicy, is_expired

# Decay constant: halves a memory's recency score every ``_HALF_LIFE_HOURS``.
_HALF_LIFE_HOURS = 72.0


def _default_weights(settings: Settings | None) -> dict[str, float]:
    return {
        "semantic": getattr(settings, "memory_retrieval_weight_semantic", 0.4),
        "recency": getattr(settings, "memory_retrieval_weight_recency", 0.2),
        "importance": getattr(settings, "memory_retrieval_weight_importance", 0.2),
        "confidence": getattr(settings, "memory_retrieval_weight_confidence", 0.2),
    }


@dataclass
class MemoryRetrievalResult:
    """A scored memory retrieved for a query."""

    memory: Memory
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)


def _parse_embedding(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(v, (int, float)) for v in parsed):
            return [float(v) for v in parsed]
    except (ValueError, TypeError):  # pragma: no cover - defensive
        return None
    return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _keyword_overlap(query: str, content: str) -> float:
    """Dice-coefficient lexical overlap between the query and a memory."""
    q_tokens = {t for t in re.findall(r"[a-z]+|\\d+", query.lower())}
    c_tokens = {t for t in re.findall(r"[a-z]+|\\d+", (content or "").lower())}
    if not q_tokens or not c_tokens:
        return 0.0
    overlap = len(q_tokens & c_tokens)
    return (2.0 * overlap) / (len(q_tokens) + len(c_tokens))


def _recency_score(created_at: datetime, now: datetime) -> float:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    age_hours = max((now - created_at).total_seconds() / 3600.0, 0.0)
    return 2 ** (-age_hours / _HALF_LIFE_HOURS)


def _semantic_matches(query_embedding: list[float] | None, memory: Memory) -> float:
    mem_vec = _parse_embedding(memory.embedding)
    if query_embedding is None or mem_vec is None:
        return 0.0
    return max(_cosine(query_embedding, mem_vec), 0.0)


class HybridRetriever:
    """Scores and ranks memories against a natural-language query."""

    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider | None = None,
        settings: Settings | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._db = db
        self._embedding_provider = embedding_provider
        self._settings = settings
        self._weights = weights or _default_weights(settings)
        #: True when the *most recent* retrieve() used the pgvector-native
        #: candidate ordering — observability for callers and the harness.
        self.last_used_pgvector: bool = False
        #: Expected native column dimension; only vectors of this width can be
        #: compared with ``<=>`` against the ``vector(1536)`` column.
        self._pgvector_dim = settings.memory_pgvector_dim if settings is not None else 1536

    async def retrieve(
        self,
        query: str,
        *,
        namespace: str,
        owner_id: UUID | None = None,
        memory_types: list[MemoryType] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
        include_expired: bool = False,
        policy: RetrievalPolicy | None = None,
    ) -> list[MemoryRetrievalResult]:
        """Return the top *top_k* memories matching *query* in *namespace*."""
        now = datetime.now(UTC)
        query_vec = None
        if self._embedding_provider is not None:
            embeddings = await self._embedding_provider.embed([query])
            if embeddings:
                query_vec = embeddings[0]

        candidates = self._fetch_candidates(
            namespace=namespace,
            owner_id=owner_id,
            memory_types=memory_types,
            include_expired=include_expired,
            now=now,
            top_k=top_k,
            query_vec=query_vec,
        )

        scored: list[MemoryRetrievalResult] = []
        for memory in candidates:
            if is_expired(memory, now) and not include_expired:
                continue
            score, breakdown = self._score(query, memory, query_vec, now)
            if score < min_score:
                continue
            scored.append(MemoryRetrievalResult(memory=memory, score=score, breakdown=breakdown))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def _fetch_candidates(
        self,
        *,
        namespace: str,
        owner_id: UUID | None,
        memory_types: list[MemoryType] | None,
        include_expired: bool,
        now: datetime,
        top_k: int,
        query_vec: list[float] | None,
    ) -> list[Memory]:
        """Fetch candidate memories within *namespace*.

        Base behavior: return every matching memory (Python-cosine path scores
        them all). When the pgvector-native path is available (PostgreSQL, the
        ``embedding_vector`` column exists, and *query_vec* matches its
        dimension) the candidates are instead pre-filtered with
        ``ORDER BY embedding_vector <=> :qv`` — a bounded prefetch of
        ``max(top_k * 5, 64)`` heads of the HNSW index — so the final blended
        score only runs over semantically-plausible rows. Failures degrade
        silently to the base set (``ProgrammingError`` on an unusable extension
        disables the feature for the request, never raises).
        """
        stmt = select(Memory).where(
            Memory.namespace == namespace,
            Memory.status == MemoryStatus.ACTIVE,
        )
        if owner_id is not None:
            stmt = stmt.where(Memory.owner_id == owner_id)
        if memory_types:
            stmt = stmt.where(Memory.type.in_(memory_types))
        if not include_expired:
            stmt = stmt.where((Memory.expires_at.is_(None)) | (Memory.expires_at > now))

        base = list(self._db.scalars(stmt).all())
        if (
            query_vec is not None
            and len(query_vec) == self._pgvector_dim
            and pgvector_enabled(self._db.get_bind())
        ):
            prefetch = max(top_k * 5, 64)
            ordered = (
                stmt.order_by(nearest_neighbours_clause())
                .params(qv=vector_literal(query_vec))
                .limit(prefetch)
            )
            try:
                self.last_used_pgvector = True
                return list(self._db.scalars(ordered).all())
            except ProgrammingError:
                # Extension/column unusable in practice — fall back to the
                # Python-cosine candidate set for this request.
                self.last_used_pgvector = False
                return base
        return base

    def _score(
        self,
        query: str,
        memory: Memory,
        query_vec: list[float] | None,
        now: datetime,
    ) -> tuple[float, dict[str, float]]:
        semantic = _semantic_matches(query_vec, memory)
        keyword = _keyword_overlap(query, memory.content)
        semantic_component = max(semantic, keyword)
        recency = _recency_score(memory.created_at, now)
        importance = memory.importance
        confidence = memory.confidence

        raw = (
            self._weights.get("semantic", 0.4) * semantic_component
            + self._weights.get("recency", 0.2) * recency
            + self._weights.get("importance", 0.2) * importance
            + self._weights.get("confidence", 0.2) * confidence
        )
        # Type weighting (if any) multiplies the whole raw score.
        if self._settings is None:
            type_multiplier = 1.0
        else:
            from app.memory.policies import RetrievalPolicy

            type_multiplier = RetrievalPolicy.from_settings(self._settings).type_multiplier(
                memory.type
            )

        score = raw * type_multiplier
        breakdown = {
            "semantic": semantic,
            "keyword": keyword,
            "recency": recency,
            "importance": importance,
            "confidence": confidence,
            "type_multiplier": type_multiplier,
        }
        return score, breakdown
