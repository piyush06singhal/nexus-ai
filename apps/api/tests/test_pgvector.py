"""pgvector-native semantic memory (PostgreSQL only).

Skipped on SQLite (the default CI/test DB). Exercises the full write->retrieve
path against a real PostgreSQL + pgvector stack so the migration, sync_vector
and native ``<=>`` ordering are all validated end to end.

Prerequisite: the compose Postgres is up and ``alembic upgrade head`` has been
applied (so the ``embedding_vector`` column exists) — exactly what the
production harness already guarantees. Point ``PGVECTOR_TEST_DATABASE_URL`` at
another database to run it elsewhere.

Marker registered in ``pyproject.toml [tool.pytest.ini_options] markers``.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401 — register all ORM tables on Base.
from app.db.models.memory import Memory, MemoryOwnerType, MemoryStatus, MemoryType
from app.db.session import Base
from app.memory.pgvector import pgvector_enabled, sync_vector
from app.memory.retrieval import HybridRetriever

# Docker compose maps the dev Postgres to host port 5433 (default credentials).
_DEFAULT_URL = "postgresql+psycopg://nexus:nexus_dev@localhost:5433/nexus"
DATABASE_URL = os.environ.get("PGVECTOR_TEST_DATABASE_URL", _DEFAULT_URL)

needs_pgvector = pytest.mark.skipif(
    not pgvector_enabled(create_engine(DATABASE_URL)),
    reason="pgvector column not present (need PostgreSQL with extension)",
)


class _Dim1536Provider:
    """Deterministic 1536-dim provider for the gated test.

    Mirrors the lexically-grounded hashing of ``MockEmbeddingProvider`` but at
    the native column's width (1536) so the ``<=>`` comparison is legal.
    """

    _DIMS = 1536

    @property
    def dimensions(self) -> int:
        return self._DIMS

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self._DIMS
            tokens = re.findall(r"[a-z]+|\\d+", text.lower())
            if not tokens:
                vector = [1.0 / math.sqrt(self._DIMS)] * self._DIMS
            else:
                for token in tokens:
                    digest = hashlib.sha256(token.encode("utf-8")).digest()
                    bucket = int.from_bytes(digest[:8], "big") % self._DIMS
                    sign = 1.0 if digest[8] & 1 else -1.0
                    vector[bucket] += sign
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            vectors.append([v / norm for v in vector])
        return vectors


def _make_memory(session: Session, *, content: str, namespace: str = "test") -> Memory:
    memory = Memory(
        namespace=namespace,
        type=MemoryType.SEMANTIC,
        owner_type=MemoryOwnerType.SYSTEM,
        owner_id=None,
        status=MemoryStatus.ACTIVE,
        content=content,
        summary=content[:60],
        confidence=1.0,
        importance=0.5,
    )
    session.add(memory)
    session.commit()
    session.refresh(memory)
    return memory


@needs_pgvector
class TestPgVectorRoundTrip:
    """Seed rows through sync_vector, then retrieve via native ordering."""

    def test_retrieve_uses_native_ordering(self) -> None:
        # Own engine/session against the PG target — no SQLite fixtures involved.
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(engine)
        session = Session(bind=engine, expire_on_commit=False)
        try:
            provider = _Dim1536Provider()
            d_alpha = _make_memory(
                session, content="Dogs are friendly animals that enjoy playing fetch"
            )
            d_beta = _make_memory(
                session,
                content="Advanced algebra covers polynomial rings and Galois theory",
            )
            d_gamma = _make_memory(
                session, content="Dogs love walks in the park and chasing squirrels"
            )

            loop = asyncio.new_event_loop()
            try:
                for memory in (d_alpha, d_beta, d_gamma):
                    vector = loop.run_until_complete(provider.embed([memory.content]))[0]
                    sync_vector(session, memory.id, vector)
                session.commit()

                retriever = HybridRetriever(session, embedding_provider=provider)
                results = loop.run_until_complete(
                    retriever.retrieve("friendly dog behavior", namespace="test", top_k=3)
                )
            finally:
                loop.close()

            assert retriever.last_used_pgvector is True, "native path not used"
            assert len(results) >= 2
            top_ids = [r.memory.id for r in results]
            assert d_beta.id not in top_ids[:2], "algebra ranked above dog memories"
            assert d_alpha.id in top_ids[:2] or d_gamma.id in top_ids[:2]
        finally:
            session.close()
            engine.dispose()
