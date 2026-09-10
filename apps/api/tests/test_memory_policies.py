"""Tests for memory retrieval & write policies (Phase 4)."""

from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.db.models.memory import Memory, MemoryType
from app.memory.policies import (
    RetrievalPolicy,
    WritePolicy,
    is_duplicate,
    is_expired,
)


def _memory(**overrides) -> Memory:
    defaults = {
        "namespace": "default",
        "type": MemoryType.SEMANTIC,
        "content": "some content",
    }
    defaults.update(overrides)
    return Memory(**defaults)


def test_retrieval_policy_defaults_from_settings():
    settings = Settings(_env_file=None)
    policy = RetrievalPolicy.from_settings(settings)
    assert policy.context_budget == settings.memory_retrieval_context_budget
    assert policy.relevance_threshold == settings.memory_retrieval_relevance_threshold
    assert policy.max_memories == settings.memory_retrieval_max_memories


def test_retrieval_policy_type_weight():
    policy = RetrievalPolicy(type_weights={MemoryType.STRUCTURED: 2.0})
    assert policy.type_multiplier(MemoryType.STRUCTURED) == 2.0
    assert policy.type_multiplier(MemoryType.SEMANTIC) == 1.0


def test_retrieval_policy_context_budget():
    policy = RetrievalPolicy(context_budget=50)
    contents = ["a" * 30, "b" * 30, "c" * 30]
    kept = policy.fit_context(contents)
    # The second item would push the total past 50, so only the first fits.
    assert kept == contents[:1]


def test_write_policy_defaults_from_settings():
    settings = Settings(_env_file=None)
    policy = WritePolicy.from_settings(settings)
    assert policy.min_importance == settings.memory_write_min_importance
    assert policy.dedup_threshold == settings.memory_write_dedup_threshold


def test_is_duplicate_same_content():
    a = _memory(content="identical text")
    b = _memory(content="identical text")
    assert is_duplicate(a, b, threshold=0.95)


def test_is_duplicate_embedding_similarity():
    import json

    # Two vectors with high cosine similarity.
    a = _memory(content="aaa", embedding=json.dumps([1.0, 0.0]))
    b = _memory(content="bbb", embedding=json.dumps([0.99, 0.01]))
    c = _memory(content="ccc", embedding=json.dumps([0.0, 1.0]))
    assert is_duplicate(a, b, threshold=0.9)
    assert not is_duplicate(a, c, threshold=0.9)


def test_is_duplicate_different_type_not_duplicate():
    a = _memory(content="same", type=MemoryType.SEMANTIC)
    b = _memory(content="same", type=MemoryType.EPISODIC)
    assert not is_duplicate(a, b, threshold=0.95)


def test_is_expired():
    past = datetime.now(UTC) - timedelta(hours=1)
    future = datetime.now(UTC) + timedelta(hours=1)
    now = datetime.now(UTC)
    assert is_expired(_memory(expires_at=past), now)
    assert not is_expired(_memory(expires_at=future), now)
    assert not is_expired(_memory(expires_at=None), now)
