"""Redis-backed rate limiter (Tier A) — unit + middleware-level tests.

The redis backend (``RATE_LIMIT_BACKEND=redis``) moves the sliding window to
a shared Redis ZSET so replicas share one rate budget. These tests verify the
counting primitives against an injectable fake, and verify the middleware
actually returns 429 *through* the redis path (not just the memory path).
A Redis outage must degrade to the in-memory window — never a 5xx.

The default backend stays ``memory`` so the rest of the suite (which never
starts Redis) is untouched.
"""

from __future__ import annotations

from collections import defaultdict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as SASession

from app.core.config import settings
from app.core.ratelimit import RedisRateLimiter
from app.db.session import get_db
from tests.test_production_chain import LOGIN, _make_user


class FakeRedis:
    """Minimal async ZSET client for the tests (no fakeredis dependency).

    ``fail=True`` simulates a Redis outage on every command so the degrades
    path is exercised.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self._zset: dict[str, dict[str, float]] = defaultdict(dict)
        self.fail = fail

    def _raise_if_down(self) -> None:
        if self.fail:
            raise ConnectionError("redis down")

    async def zremrangebyscore(self, key, min_score, max_score) -> int:
        self._raise_if_down()
        before = len(self._zset[key])
        self._zset[key] = {
            m: s for m, s in self._zset[key].items() if not (min_score <= s <= max_score)
        }
        return before - len(self._zset[key])

    async def zcard(self, key) -> int:
        self._raise_if_down()
        return len(self._zset[key])

    async def zadd(self, key, mapping) -> int:
        self._raise_if_down()
        self._zset[key].update(mapping)
        return len(mapping)

    async def expire(self, key, ttl) -> bool:
        self._raise_if_down()
        return True


# ── counting primitive ──────────────────────────────────────────────────────


def _allow(limiter: RedisRateLimiter, ip: str, cls: str, limit: int) -> bool:
    """Run one ``allow`` on a fresh event loop (sync-test convenience)."""
    import asyncio

    return asyncio.run(limiter.allow(ip, cls, limit))


def test_redis_allows_below_limit_blocks_at_limit():
    limiter = RedisRateLimiter(client=FakeRedis())
    # limit=2 → exactly two through, third blocked.
    assert _allow(limiter, "1.2.3.4", "auth", 2) is True
    assert _allow(limiter, "1.2.3.4", "auth", 2) is True
    assert _allow(limiter, "1.2.3.4", "auth", 2) is False
    # Different ip / different class → independent budget.
    assert _allow(limiter, "1.2.3.4", "default", 2) is True
    assert _allow(limiter, "9.9.9.9", "auth", 2) is True


def test_redis_window_prunes_stale_entries():
    import time

    limiter = RedisRateLimiter(client=FakeRedis())
    fake = limiter._client  # type: ignore[attr-defined]
    key = "rl:1.2.3.4:auth"
    old = time.time() - 120  # outside the 60s window
    fake._zset[key] = {f"{old}:1": old, f"{old}:2": old}
    # Both members are stale → pruned before the count, so limit=1 admits.
    assert _allow(limiter, "1.2.3.4", "auth", 1) is True
    assert len(fake._zset[key]) == 1  # exactly the fresh entry remains


def test_redis_outage_degrades_to_memory_without_raising():
    import time

    limiter = RedisRateLimiter(client=FakeRedis(fail=True))
    # A down Redis must never raise — the request degrades to the local window.
    assert _allow(limiter, "1.2.3.4", "auth", 5) is True
    assert _allow(limiter, "1.2.3.4", "auth", 5) is True
    # The degraded memory window still enforces the cap: 3 more hits → blocked.
    now = time.monotonic()
    limiter._memory._traffic[("1.2.3.4", "auth")].extend([now, now, now])
    assert _allow(limiter, "1.2.3.4", "auth", 5) is False
    assert limiter._warned is True


# ── middleware through the redis path ────────────────────────────────────────


@pytest.fixture
def redis_prod_client(db_engine, monkeypatch):
    """A fresh app with AUTH + RATE_LIMIT on AND ``rate_limit_backend=redis``.

    ``rate_limit_backend`` is read once at middleware construction, so it must
    be set before ``create_app``. ``redis.asyncio.from_url`` is pointed at a
    fake so the injected limiter never dials a real server.
    """
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_backend", "redis")

    fake = FakeRedis()

    import redis.asyncio as aioredis

    monkeypatch.setattr(aioredis, "from_url", lambda *a, **k: fake)

    from app.main import create_app

    def override_get_db():
        with SASession(bind=db_engine, expire_on_commit=False) as session:
            yield session

    fresh_app = create_app()
    fresh_app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(fresh_app) as client:
            yield client, db_engine, fake
    finally:
        fresh_app.dependency_overrides.clear()


def test_redis_backend_enforces_429_through_middleware(redis_prod_client, monkeypatch):
    client, db_engine, fake = redis_prod_client

    with SASession(bind=db_engine) as db:
        _make_user(db)

    # Cap auth at 1, then exceed it → the redis path must return 429.
    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 1)

    ok = client.post("/api/v1/auth/login", json=LOGIN)
    assert ok.status_code == 200, ok.text

    blocked = client.post("/api/v1/auth/login", json=LOGIN)
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["error"]["code"] == "rate_limited"

    # The budget lives in the ZSET — the fake observed the writes.
    assert any(k.startswith("rl:") for k in fake._zset)


def test_redis_backend_degrades_on_outage_returns_200(redis_prod_client, monkeypatch):
    client, db_engine, fake = redis_prod_client

    with SASession(bind=db_engine) as db:
        _make_user(db)

    # Redis dies mid-request → the memory fallback keeps serving (no 5xx).
    fake.fail = True
    resp = client.post("/api/v1/auth/login", json=LOGIN)
    assert resp.status_code == 200, resp.text
