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
def db_engine():
    """An in-memory SQLite engine with all NEXUS tables created."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.db.session import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(db_engine):
    """Yield a standalone SQLAlchemy Session bound to the in-memory engine."""
    from sqlalchemy.orm import Session

    with Session(bind=db_engine, expire_on_commit=False) as session:
        yield session


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
