"""Rate-limiting counting primitives (Phase 11, Tier A).

``RateLimitMiddleware`` owns the route-tiering (which class a request
belongs to and that class's per-minute limit); this module owns *counting*.
Two backends are available behind ``RATE_LIMIT_BACKEND``:

- ``memory`` (default) — per-process sliding-window deques. This is the
  original behaviour and is what the test suite exercises.
- ``redis`` — a cross-process sliding window over one Redis ZSET per key
  (``rl:{ip}:{route_class}``), so multiple API replicas share a single
  rate budget. Added in the Tier A upgrade.

The Redis path is designed to never fail a request: **any** Redis error
(connection refused, timeout, server/out-of-memory) degrades that request
to the local in-memory window and logs one warning line per process. A
Redis outage therefore shows up as a fraction of requests unpaced — never
as a 5xx.

The async client is built lazily on first use (not at import or app
startup), so deployments that never enable the redis backend instantiate
no Redis connection at all. ``client`` is an injectable seam for tests (a
tiny fake implementing ``zremrangebyscore``/``zcard``/``zadd``/``expire``).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Sliding window length in seconds (must match the in-memory limiter).
_WINDOW = 60.0


class RateLimiter:
    """Counting primitive for :class:`~app.core.middleware.RateLimitMiddleware`.

    ``allow(ip, route_class, limit)`` is the only API: ``True`` lets the
    request through, ``False`` means the caller should return 429.
    """

    async def allow(self, ip: str, route_class: str, limit: int) -> bool:
        raise NotImplementedError


class MemoryRateLimiter(RateLimiter):
    """Single-process sliding-window limiter (deque of timestamps per key)."""

    def __init__(self) -> None:
        self._traffic: dict[tuple[str, str], deque] = defaultdict(deque)

    async def allow(self, ip: str, route_class: str, limit: int) -> bool:
        bucket = self._traffic[(ip, route_class)]
        now = time.monotonic()
        while bucket and now - bucket[0] > _WINDOW:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


class RedisRateLimiter(RateLimiter):
    """Cross-process sliding-window limiter backed by a Redis ZSET.

    Each key holds event timestamps; expired members are pruned before the
    count is checked. Any Redis failure degrades the request to the local
    in-memory window (see module docstring).
    """

    def __init__(self, *, client=None) -> None:
        # ``client`` is a test seam (an async object with the Redis ZSET
        # commands, or None to build a real ``redis.asyncio`` client lazily).
        self._client = client
        self._memory = MemoryRateLimiter()
        self._warned = False

    def _build_client(self):
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._client

    async def _allow_redis(self, client, ip: str, route_class: str, limit: int) -> bool:
        key = f"rl:{ip}:{route_class}"
        now = time.time()
        await client.zremrangebyscore(key, 0, now - _WINDOW)
        count = await client.zcard(key)
        if count >= limit:
            return False
        # Unique member per hit (timestamp + monotonic ns) avoids ZSET
        # collisions when two hits land in the same wall-clock instant.
        await client.zadd(key, {f"{now}:{time.monotonic_ns()}": now})
        await client.expire(key, int(_WINDOW * 2))
        return True

    async def allow(self, ip: str, route_class: str, limit: int) -> bool:
        try:
            client = self._build_client()
            return await self._allow_redis(client, ip, route_class, limit)
        except Exception as exc:  # noqa: BLE001 - any Redis failure degrades
            if not self._warned:
                self._warned = True
                logger.warning(
                    "redis_rate_limiter_degraded_to_memory",
                    extra={"error": str(exc)[:300], "key": f"{ip}:{route_class}"},
                )
            return await self._memory.allow(ip, route_class, limit)
