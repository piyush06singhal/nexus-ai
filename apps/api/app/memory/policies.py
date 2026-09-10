"""Memory retrieval & write policies.

Policies encode the "how much / how fresh / how relevant" decisions when the
runtime both retrieves memories to inject into context and writes new memories
to storage. They keep the retriever and service focused on mechanics while the
business rules (context budget, relevance threshold, dedup, TTL) live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.db.models.memory import Memory, MemoryType


@dataclass
class RetrievalPolicy:
    """Controls how many memories are retrieved and how much fits in context.

    Attributes:
        context_budget: Soft cap on the total characters of memory content
            injected into a context window.
        relevance_threshold: Minimum combined score for a memory to be retained.
        max_memories: Hard cap on the number of memories returned.
        type_weights: Per-type score multipliers (boosts structured vs working).
    """

    context_budget: int = 5000
    relevance_threshold: float = 0.3
    max_memories: int = 20
    type_weights: dict[MemoryType, float] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, settings) -> RetrievalPolicy:
        """Build a policy from a Settings instance (falls back to defaults)."""
        return cls(
            context_budget=getattr(settings, "memory_retrieval_context_budget", 5000),
            relevance_threshold=getattr(settings, "memory_retrieval_relevance_threshold", 0.3),
            max_memories=getattr(settings, "memory_retrieval_max_memories", 20),
        )

    def type_multiplier(self, memory_type: MemoryType) -> float:
        return self.type_weights.get(memory_type, 1.0)

    def fit_context(self, contents: list[str]) -> list[str]:
        """Return the leading subset of *contents* that fits the budget."""
        total = 0
        kept: list[str] = []
        for text in contents:
            cost = len(text)
            if total + cost > self.context_budget and kept:
                break
            total += cost
            kept.append(text)
        return kept


@dataclass
class WritePolicy:
    """Controls what is stored and for how long.

    Attributes:
        min_importance: Memories below this importance are not stored.
        dedup_threshold: Cosine similarity above this marks a near-duplicate.
        max_working: Cap on WORKING memories per owner (oldest pruned).
        default_ttl_hours: TTL for working memory when none is given.
    """

    min_importance: float = 0.1
    dedup_threshold: float = 0.95
    max_working: int = 50
    default_ttl_hours: int = 24

    @classmethod
    def from_settings(cls, settings) -> WritePolicy:
        """Build a policy from a Settings instance (falls back to defaults)."""
        return cls(
            min_importance=getattr(settings, "memory_write_min_importance", 0.1),
            dedup_threshold=getattr(settings, "memory_write_dedup_threshold", 0.95),
            max_working=getattr(settings, "memory_write_max_working", 50),
            default_ttl_hours=getattr(settings, "memory_write_default_ttl_hours", 24),
        )


def is_duplicate(candidate: Memory, existing: Memory, threshold: float) -> bool:
    """Return whether *candidate* is a near-duplicate of *existing*.

    Uses the candidate's embedding (or its importance as a weak proxy) to
    decide. A high cosine similarity means we already know this.
    """
    cand_vec = _parse_embedding(candidate.embedding)
    exist_vec = _parse_embedding(existing.embedding)
    if cand_vec and exist_vec:
        similarity = _cosine(cand_vec, exist_vec)
        return similarity >= threshold
    # Fallback: same type + identical (or near-identical) content is a dup.
    return candidate.type == existing.type and candidate.content.strip().lower() == (
        existing.content.strip().lower()
    )


def _parse_embedding(raw: str | None) -> list[float] | None:
    """Parse a text-serialized vector back into a list of floats."""
    if not raw:
        return None
    try:
        import json

        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(v, (int, float)) for v in parsed):
            return [float(v) for v in parsed]
    except (ValueError, TypeError):  # pragma: no cover - defensive
        return None
    return None


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def is_expired(memory: Memory, now) -> bool:
    """Return whether *memory* has passed its voluntary TTL expiry."""
    if memory.expires_at is None:
        return False
    expires_at = memory.expires_at
    if expires_at.tzinfo is None:
        from datetime import UTC

        expires_at = expires_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        from datetime import UTC

        now = now.replace(tzinfo=UTC)
    return expires_at < now
