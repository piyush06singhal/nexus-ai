"""Circuit breaker for outbound external providers (§reliability).

Simple 3-state breaker (CLOSED → OPEN on threshold failures → HALF_OPEN probe →
CLOSED on success). Bounded and deterministic so tests can assert state
transitions.
"""

from __future__ import annotations

import time
from threading import Lock


class CircuitBreakerState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Trip after *threshold* consecutive failures, reset after *reset_seconds*."""

    def __init__(self, *, threshold: int = 5, reset_seconds: int = 30) -> None:
        self.threshold = max(threshold, 1)
        self.reset_seconds = reset_seconds
        self._state = CircuitBreakerState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._lock = Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == CircuitBreakerState.OPEN and (
                time.monotonic() - self._opened_at >= self.reset_seconds
            ):
                self._state = CircuitBreakerState.HALF_OPEN
            return self._state

    def allow_request(self) -> bool:
        return self.state != CircuitBreakerState.OPEN

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = CircuitBreakerState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.OPEN
                self._opened_at = time.monotonic()
                self._failures = 1
                return
            self._failures += 1
            if self._failures >= self.threshold:
                self._state = CircuitBreakerState.OPEN
                self._opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = CircuitBreakerState.CLOSED

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "consecutive_failures": self._failures,
            "threshold": self.threshold,
            "reset_seconds": self.reset_seconds,
        }
