"""Tests for hybrid memory retrieval (Phase 4)."""

import asyncio
from uuid import uuid4

from app.db.models.memory import Memory, MemoryStatus, MemoryType
from app.memory.embedding import MockEmbeddingProvider
from app.memory.retrieval import HybridRetriever


def _seed(db, *, namespace="default", content, **overrides):
    defaults = {
        "namespace": namespace,
        "type": MemoryType.SEMANTIC,
        "content": content,
        "status": MemoryStatus.ACTIVE,
        "importance": 0.5,
        "confidence": 1.0,
    }
    defaults.update(overrides)
    memory = Memory(**defaults)
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def _retrieve(**kwargs):
    """Run a synchronous retrieval against the given db."""
    return asyncio.run(HybridRetriever(kwargs.pop("db")).retrieve(**kwargs))


def test_keyword_retrieval_no_embeddings(db):
    _seed(db, content="the sales report shows revenue growth")
    _seed(db, content="a recipe for pasta carbonara")
    results = _retrieve(db=db, query="sales revenue", namespace="default", top_k=5)
    assert len(results) == 2
    # The sales memory should rank first due to keyword overlap.
    assert "sales" in results[0].memory.content.lower()


def test_keyword_with_negative_signal_can_still_match(db):
    _seed(db, content="project alpha delivery status")
    _seed(db, content="grocery shopping list")
    results = _retrieve(db=db, query="project delivery", namespace="default", top_k=5)
    assert results
    assert "project" in results[0].memory.content.lower()


def test_namespace_isolation(db):
    _seed(db, namespace="teamA", content="confidential Alpha output")
    _seed(db, namespace="teamB", content="confidential Alpha output")
    results = _retrieve(db=db, query="Alpha", namespace="teamA", top_k=5)
    assert len(results) == 1
    assert results[0].memory.namespace == "teamA"


def test_owner_scoping(db):
    owner_a = uuid4()
    owner_b = uuid4()
    _seed(db, content="sensitive memory", owner_id=owner_a)
    _seed(db, content="sensitive memory", owner_id=owner_b)
    results = _retrieve(db=db, query="sensitive", namespace="default", owner_id=owner_a, top_k=5)
    assert len(results) == 1
    assert results[0].memory.owner_id == owner_a


def test_type_filtering(db):
    _seed(db, content="episodic detail", type=MemoryType.EPISODIC)
    _seed(db, content="episodic detail", type=MemoryType.SEMANTIC)
    results = _retrieve(
        db=db,
        query="episodic",
        namespace="default",
        memory_types=[MemoryType.EPISODIC],
        top_k=5,
    )
    assert len(results) == 1
    assert results[0].memory.type == MemoryType.EPISODIC


def test_min_score_filtering(db):
    _seed(db, content="totally unrelated topic xyz")
    results = _retrieve(
        db=db, query="completelydifferentqueryxyz", namespace="default", min_score=0.99
    )
    assert results == []


def test_expired_excluded_by_default(db):
    from datetime import UTC, datetime, timedelta

    _seed(
        db,
        content="stale working note",
        type=MemoryType.WORKING,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    results = _retrieve(db=db, query="stale working note", namespace="default")
    assert results == []


def test_importance_rank(db):
    _seed(db, content="alpha beta", importance=0.9)
    _seed(db, content="alpha beta", importance=0.1)
    results = _retrieve(db=db, query="alpha", namespace="default", top_k=5)
    assert results[0].memory.importance == 0.9


def test_breakdown_present(db):
    _seed(db, content="delta gamma", importance=0.7)
    results = _retrieve(db=db, query="delta", namespace="default", top_k=1)
    assert len(results) == 1
    for key in ("semantic", "keyword", "recency", "importance", "confidence"):
        assert key in results[0].breakdown


def test_semantic_retrieval_with_mock_embeddings(db):
    provider = MockEmbeddingProvider()
    for text in ["customer onboarding workflow", "pizza dough recipe"]:
        (v,) = asyncio.run(provider.embed([text]))
        import json

        _seed(db, content=text, embedding=json.dumps(v))
    retriever = HybridRetriever(db, embedding_provider=provider)
    results = asyncio.run(
        retriever.retrieve("customer onboarding workflow", namespace="default", top_k=5)
    )
    assert results
    assert "onboarding" in results[0].memory.content.lower()
