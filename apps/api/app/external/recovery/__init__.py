"""External failure ↔ Phase 6 recovery mapping (Phase 10, §60)."""

from __future__ import annotations

from app.external.recovery.mapping import (
    classify_exception,
    classify_external_failure,
    retryable,
    strategy_for,
)

__all__ = ["classify_exception", "classify_external_failure", "retryable", "strategy_for"]
