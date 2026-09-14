"""pgvector-native semantic memory support (PostgreSQL only).

The ORM ``Memory`` model keeps a portable ``embedding`` Text column (a JSON
array of floats) so the whole memory system runs unchanged on SQLite in tests
and local dev — the Python-cosine path in :mod:`app.memory.retrieval` is the
always-available fallback. On PostgreSQL, migration *0015_pgvector* additionally
creates a native ``embedding_vector vector(1536)`` column (pgvector extension,
HNSW index). This module is the bridge between the two:

- :func:`pgvector_enabled` — cheap, cached, never-raising probe: is this engine
  PostgreSQL *and* does the native column exist?
- :func:`sync_vector` — mirror a portable embedding into the native column on
  write (a raw ``UPDATE`` because the ORM model deliberately has no knowledge of
  the extension-only column).
- :func:`nearest_neighbours` — a raw ordering clause + bound parameter for the
  retrieval layer to use, keeping the ORM filters intact.

Everything here is off by default: on SQLite, or on Postgres without the
extension, the functions are no-ops and the system degrades to the Python path.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from sqlalchemy import text

#: Per-engine cache key in ``Engine.info`` — the schema is fixed for the life
#: of a process, so we probe it at most once per engine.
_ENGINE_ATTR = "_nexus_pgvector_enabled"


def _probe(pg_engine: Any) -> bool:
    """Inspect the catalog for the native column; never raises."""
    with contextlib.suppress(Exception):
        from sqlalchemy import inspect

        inspector = inspect(pg_engine)
        if not inspector.has_table("memories"):
            return False
        columns = {c["name"] for c in inspector.get_columns("memories")}
        return "embedding_vector" in columns
    return False


def pgvector_enabled(bind: Any) -> bool:
    """True when *bind* is PostgreSQL and the native column exists.

    *bind* is either an :class:`Engine` or a :class:`Session` (both expose
    ``dialect`` and ``info``). The result is cached per engine so callers probe
    the schema at most once per process; a transient catalog failure simply
    returns False and the Python-cosine path stays in charge.
    """
    if getattr(bind, "dialect", None) is None:
        return False
    if bind.dialect.name != "postgresql":
        return False
    info = getattr(bind, "info", None)
    if not isinstance(info, dict):
        return _probe(bind)
    if _ENGINE_ATTR not in info:
        info[_ENGINE_ATTR] = _probe(bind)
    return bool(info[_ENGINE_ATTR])


def sync_vector(db: Any, memory_id: Any, vector: list[float]) -> None:
    """Mirror *vector* into ``memories.embedding_vector`` (PostgreSQL only).

    A best-effort additive write: guardrails are off by default (no-op on
    SQLite or when the column is absent), and any execution error is swallowed
    so a failed native write never breaks a run — the portable Text column is
    the source of truth for the Python path regardless.
    """
    if not pgvector_enabled(db.get_bind()):
        return
    with contextlib.suppress(Exception):
        db.execute(
            text("UPDATE memories SET embedding_vector = (:vec)::vector WHERE id = :id"),
            {"vec": json.dumps(vector), "id": memory_id},
        )


def nearest_neighbours_clause() -> Any:
    """A raw ``<=>`` ordering expression bound to a ``:qv`` cast to vector.

    Used only when :func:`pgvector_enabled` is True; the caller supplies the
    vector literal via ``stmt.params(qv=json.dumps(vector))``.
    """
    return text("memories.embedding_vector <=> (:qv)::vector")


def vector_literal(vector: list[float]) -> str:
    """Serialize *vector* into the pgvector literal syntax ``[0.1, 0.2, ...]``."""
    return json.dumps(vector)
