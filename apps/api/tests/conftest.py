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
