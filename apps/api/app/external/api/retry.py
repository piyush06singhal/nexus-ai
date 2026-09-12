"""Retry policy for outbound external requests (Phase 10).

Reuses the Phase 6 strategy vocabulary: retryable failures are retried with an
exponential backoff bounded by ``external_action_timeout_seconds``. Idempotent
capabilities may be retried safely; non-idempotent ones are never auto-retried
(§8).
"""

from __future__ import annotations


def backoff_delay_ms(attempt: int, *, base_ms: int = 200, max_ms: int = 2000) -> int:
    """Exponential backoff for a zero-based attempt index."""
    return min(base_ms * (2**attempt), max_ms)


def is_retryable_status_code(status_code: int) -> bool:
    """HTTP statuses that warrant a bounded retry."""
    return status_code in (408, 425, 429, 500, 502, 503, 504)


def is_rate_limit_status(status_code: int) -> bool:
    return status_code == 429


def max_attempts_for(severity: str, *, hard_cap: int = 3) -> int:
    """Bounded retry budget mirroring Phase 6 severity→attempts."""
    budget = {"low": 3, "medium": 2, "high": 1, "critical": 0}
    return max(0, min(budget.get(severity, 1), hard_cap))
