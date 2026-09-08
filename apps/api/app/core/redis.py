"""Redis connection management.

Provides a lazily-created Redis client factory. The client is created on
first use and cached for the process lifetime. Connection failures are
surfaced to callers and reported via the health endpoint; they never crash
startup. This keeps the core API operational even if Redis is temporarily
unavailable.
"""

from functools import lru_cache

import redis.asyncio as aioredis

from app.core.config import settings


@lru_cache
def get_redis_client() -> aioredis.Redis:
    """Return a cached async Redis client."""
    return aioredis.from_url(settings.redis_url, decode_responses=True)
