"""Recovery package (Phase 6).

The recovery engine detects, diagnoses, and recovers from execution failures
through a bounded, policy-driven state machine. Recovery never broadens
permissions (§45), is bounded by budgets (§48), and reuses existing runtime
abstractions (§55).
"""

from app.recovery.engine import RecoveryEngine
from app.recovery.types import RecoveryAttempt, RecoveryPlan

__all__ = [
    "RecoveryEngine",
    "RecoveryPlan",
    "RecoveryAttempt",
]
