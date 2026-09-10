"""Recovery state machine (Phase 6, spec §17).

Enforces valid state transitions for the recovery lifecycle. Each transition
is logged for observability and audit trails.

State flow::

    DETECTED → CLASSIFIED → RECOVERY_PLANNED → RECOVERING
        → { RETRYING | REPLANNING | FALLBACK }
        → REVERIFIED → RECOVERED
        Terminal: RECOVERED | FAILED | ESCALATED | ABORTED | PARTIALLY_RECOVERED
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.recovery.types import RecoveryState


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


# ── Valid transitions (from → set of allowed targets) ─────────────────────────

_VALID_TRANSITIONS: dict[RecoveryState, frozenset[RecoveryState]] = {
    RecoveryState.DETECTED: frozenset({RecoveryState.CLASSIFIED}),
    RecoveryState.CLASSIFIED: frozenset({RecoveryState.RECOVERY_PLANNED, RecoveryState.ESCALATED}),
    RecoveryState.RECOVERY_PLANNED: frozenset(
        {RecoveryState.RECOVERING, RecoveryState.ESCALATED, RecoveryState.ABORTED}
    ),
    RecoveryState.RECOVERING: frozenset(
        {
            RecoveryState.RETRYING,
            RecoveryState.REPLANNING,
            RecoveryState.FALLBACK,
            RecoveryState.RECOVERED,
        }
    ),
    RecoveryState.RETRYING: frozenset(
        {
            RecoveryState.RECOVERING,
            RecoveryState.REVERIFIED,
            RecoveryState.REPLANNING,
            RecoveryState.FALLBACK,
            RecoveryState.FAILED,
            RecoveryState.ESCALATED,
        }
    ),
    RecoveryState.REPLANNING: frozenset(
        {RecoveryState.RECOVERY_PLANNED, RecoveryState.ESCALATED, RecoveryState.ABORTED}
    ),
    RecoveryState.FALLBACK: frozenset(
        {
            RecoveryState.RECOVERING,
            RecoveryState.REVERIFIED,
            RecoveryState.RECOVERED,
            RecoveryState.FAILED,
            RecoveryState.PARTIALLY_RECOVERED,
        }
    ),
    RecoveryState.REVERIFIED: frozenset(
        {RecoveryState.RECOVERED, RecoveryState.FAILED, RecoveryState.ESCALATED}
    ),
    # Terminal states — no transitions out
    RecoveryState.RECOVERED: frozenset(),
    RecoveryState.FAILED: frozenset(),
    RecoveryState.ESCALATED: frozenset(),
    RecoveryState.ABORTED: frozenset(),
    RecoveryState.PARTIALLY_RECOVERED: frozenset(),
}


class RecoveryStateMachine:
    """Enforces and records state transitions for the recovery engine."""

    def __init__(self) -> None:
        self._state: RecoveryState = RecoveryState.DETECTED
        self._timeline: list[dict[str, Any]] = []
        self._started_at: datetime = datetime.now(UTC)

    @property
    def state(self) -> RecoveryState:
        return self._state

    @property
    def timeline(self) -> list[dict[str, Any]]:
        return list(self._timeline)

    @property
    def is_terminal(self) -> bool:
        """Whether the state machine is in a terminal state."""
        return len(_VALID_TRANSITIONS.get(self._state, frozenset())) == 0

    def can_transition(self, target: RecoveryState) -> bool:
        """Check if a transition to *target* is valid from the current state."""
        allowed = _VALID_TRANSITIONS.get(self._state, frozenset())
        return target in allowed

    def transition(
        self,
        target: RecoveryState,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Execute a transition, raising if invalid.

        Args:
            target: The target state.
            reason: Why the transition is being made.
            metadata: Additional context for the timeline entry.

        Raises:
            InvalidTransitionError: If the transition is not valid.
        """
        if not self.can_transition(target):
            raise InvalidTransitionError(
                f"Cannot transition from {self._state.value} to {target.value}"
            )

        now = datetime.now(UTC)
        entry = {
            "from": self._state.value,
            "to": target.value,
            "reason": reason,
            "metadata": metadata,
            "timestamp": now.isoformat(),
        }
        self._timeline.append(entry)
        self._state = target

    def reset(self) -> None:
        """Reset the state machine to DETECTED (for testing)."""
        self._state = RecoveryState.DETECTED
        self._timeline.clear()
        self._started_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "is_terminal": self.is_terminal,
            "timeline": self._timeline,
            "started_at": self._started_at.isoformat(),
        }
