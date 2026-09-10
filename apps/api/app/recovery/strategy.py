"""Recovery strategies (Phase 6, spec §15).

Each strategy has explicit safety conditions and a defined behavior. The
strategies are evaluated by the :class:`RecoveryPlanner` and executed by the
:class:`RecoveryEngine`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RecoveryStrategy(StrEnum):
    """Available recovery strategies (spec §15)."""

    RETRY = "retry"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    RETRY_WITH_MODIFIED_INPUT = "retry_with_modified_input"
    REPLAN = "replan"
    FALLBACK_AGENT = "fallback_agent"
    FALLBACK_TOOL = "fallback_tool"
    SKIP = "skip"
    PARTIAL_COMPLETION = "partial_completion"
    ESCALATE = "escalate"
    ABORT = "abort"


@dataclass
class StrategyConditions:
    """Safety conditions for a recovery strategy."""

    requires_safety_check: bool = False
    requires_budget: bool = True
    max_consecutive: int = 3
    idempotent_required: bool = False
    needs_human_approval: bool = False
    description: str = ""


_STRATEGY_CONDITIONS: dict[RecoveryStrategy, StrategyConditions] = {
    RecoveryStrategy.RETRY: StrategyConditions(
        description="Simple retry with no changes",
        requires_safety_check=False,
        max_consecutive=3,
    ),
    RecoveryStrategy.RETRY_WITH_BACKOFF: StrategyConditions(
        description="Retry with exponential backoff",
        requires_safety_check=False,
        max_consecutive=3,
    ),
    RecoveryStrategy.RETRY_WITH_MODIFIED_INPUT: StrategyConditions(
        description="Retry with simplified/modified input",
        requires_safety_check=False,
        max_consecutive=2,
    ),
    RecoveryStrategy.REPLAN: StrategyConditions(
        description="Generate a new plan and execute it",
        requires_safety_check=True,
        max_consecutive=1,
    ),
    RecoveryStrategy.FALLBACK_AGENT: StrategyConditions(
        description="Use an alternative agent with different capabilities",
        requires_safety_check=True,
        max_consecutive=1,
    ),
    RecoveryStrategy.FALLBACK_TOOL: StrategyConditions(
        description="Use an alternative tool for the same task",
        requires_safety_check=True,
        max_consecutive=1,
    ),
    RecoveryStrategy.SKIP: StrategyConditions(
        description="Skip this step and continue with the next",
        requires_budget=False,
        max_consecutive=1,
    ),
    RecoveryStrategy.PARTIAL_COMPLETION: StrategyConditions(
        description="Record partial completion and move on",
        requires_budget=False,
        max_consecutive=1,
    ),
    RecoveryStrategy.ESCALATE: StrategyConditions(
        description="Escalate to human for review",
        requires_budget=False,
        needs_human_approval=True,
        max_consecutive=1,
    ),
    RecoveryStrategy.ABORT: StrategyConditions(
        description="Abort the recovery and mark as failed",
        requires_budget=False,
        max_consecutive=1,
    ),
}


def strategy_safety_conditions(strategy: RecoveryStrategy) -> StrategyConditions:
    """Get the safety conditions for a recovery strategy."""
    return _STRATEGY_CONDITIONS.get(strategy, StrategyConditions())


def strategy_backoff_ms(attempt: int, base_ms: int = 1000, max_ms: int = 30000) -> int:
    """Compute backoff delay for retry_with_backoff strategy.

    Uses exponential backoff with jitter: base * 2^attempt, capped at max_ms.
    """
    import random

    delay = base_ms * (2 ** min(attempt, 10))
    # Add jitter (±25%)
    jitter = delay * 0.25
    delay = int(delay + random.uniform(-jitter, jitter))
    return max(0, min(delay, max_ms))
