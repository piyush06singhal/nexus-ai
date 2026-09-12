"""In-memory sliding-window rate limiter for outbound external requests."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime
from threading import Lock


class RateLimiter:
    """Sliding-window rate limiter keyed by (provider|company).

    Thread-safe; bounds how many requests a key may make per window. The
    default derives from ``external_rate_limit_per_minute``.
    """

    def __init__(self, default_per_minute: int = 60) -> None:
        self._window_seconds = 60.0
        self._default = max(default_per_minute, 1)
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def allow(self, key: str, *, per_minute: int | None = None) -> bool:
        limit = max(per_minute or self._default, 1)
        now = time.monotonic()
        with self._lock:
            window_start = now - self._window_seconds
            hits = [t for t in self._hits[key] if t > window_start]
            hits.append(now)
            self._hits[key] = hits
            return len(hits) <= limit

    def remaining(self, key: str, *, per_minute: int | None = None) -> int:
        limit = max(per_minute or self._default, 1)
        now = time.monotonic()
        with self._lock:
            window_start = now - self._window_seconds
            hits = [t for t in self._hits[key] if t > window_start]
            return max(0, limit - len(hits))

    def reset_key(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def rate_limit_epoch(self) -> str:
        """Human-readable window start for observability."""
        return datetime.now(UTC).isoformat()
