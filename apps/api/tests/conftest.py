"""Shared fixtures for backend tests.

Tests do not require a live PostgreSQL/Redis. The ``get_db`` dependency and
the Redis health probe are overridden with deterministic fakes so the unit
suite runs anywhere, including CI without Docker.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db


class StubSession:
    """Stand-in for the DB session; reports a fixed ``SELECT 1`` outcome."""

    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy

    def execute(self, *_args, **_kwargs):
        if not self.healthy:
            raise RuntimeError("database unavailable")
        return None

    def close(self) -> None:
        pass


@pytest.fixture
def healthy_client(monkeypatch):
    """Test client where both DB and Redis report healthy."""
    from app.api.v1.endpoints import health as health_module
    from app.main import app

    app.dependency_overrides[get_db] = lambda: StubSession(healthy=True)
    monkeypatch.setattr(
        health_module, "_check_redis", lambda: health_module.ServiceCheck(status="ok")
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def degraded_client(monkeypatch):
    """Test client whose DB and Redis checks fail, reporting degraded health."""
    from app.api.v1.endpoints import health as health_module
    from app.main import app

    app.dependency_overrides[get_db] = lambda: StubSession(healthy=False)
    monkeypatch.setattr(
        health_module, "_check_redis", lambda: health_module.ServiceCheck(status="degraded")
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# SQLite-backed DB/session fixtures for service, runtime, and API tests.
# In-memory SQLite with StaticPool shares one connection across sessions so the
# service layer (which builds its own sessionsc via DB and commits) works without
# a live PostgreSQL. Keeps the suite runnable anywhere, incl. CI without Docker.
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine(tmp_path):
    """A file-backed SQLite engine with all NEXUS tables created.

    A normal (Queue) connection pool backed by a temp file gives every session
    (including the parallel worker sessions spawned by the orchestration engine)
    its own connection to the *same* database. This is what makes true parallel
    task execution test-safe — a single Statically-pooled in-memory connection
    would serialize a worker commit behind the request session's open
    transaction and raise ``cannot commit transaction - SQL statements in
    progress``.
    """
    from sqlalchemy import create_engine

    import app.db.models  # noqa: F401 — ensures all ORM tables are registered.
    from app.db.session import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        # ``timeout`` is SQLite's busy timeout (seconds): parallel worker
        # threads write to the same file, and writers wait for the lock instead
        # of throwing "database is locked".
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    # WAL journaling — the practical fix for the pre-existing full-suite flake
    # in test_orchestration_integration.py: orchestration workers run multiple
    # concurrent *writer* connections against this same file DB, and under full
    # suite load the rollback-journal ATOMIC-write lock window could exceed the
    # busy timeout and fail a task ("database is locked"). WAL lets readers
    # never block writers and shrinks writer-vs-writer contention, so the
    # pipeline tolerates the suite's real-world load. Behavior-neutral: rows,
    # fixtures, and assertions are unchanged.
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, _record):  # pragma: no cover - exercised implicitly
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
        finally:
            cur.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(db_engine):
    """Yield a standalone SQLAlchemy Session bound to the in-memory engine."""
    from sqlalchemy.orm import Session

    with Session(bind=db_engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def phase6_settings(monkeypatch):
    """Enable Phase 6 verification/recovery/evaluation settings (deterministic)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "verification_enabled", True)
    monkeypatch.setattr(settings, "recovery_enabled", True)
    monkeypatch.setattr(settings, "failure_injection_enabled", True)
    monkeypatch.setattr(settings, "recovery_execute_sync", True)
    monkeypatch.setattr(settings, "escalation_auto_approve", False)
    return settings


@pytest.fixture
def api_client(db_engine):
    """Test client with get_db overridden to serve the in-memory SQLite DB.

    The runtime and provider are also overridden so agent/task/execution
    workflows can be exercised end-to-end without a real model provider.
    """
    from sqlalchemy.orm import Session as SASession

    from app.main import app

    def override_get_db():
        with SASession(bind=db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
