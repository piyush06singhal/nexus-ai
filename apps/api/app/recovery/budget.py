"""Execution budget and tracker (Phase 6, spec §48).

Bounded recovery: never ``while not success: retry()``. The budget limits
retries, verification attempts, runtime, tokens, cost, and tool calls.
When exhausted, the system stops and records the reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionBudget:
    """Configurable budget constraints for recovery (spec §48)."""

    max_retries: int = 3
    max_verification_attempts: int = 2
    max_runtime_seconds: int = 300
    max_tokens: int = 100_000
    max_cost: float = 1.0
    tool_call_budget: int = 10

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ExecutionBudget:
        if not data:
            return cls()
        return cls(
            max_retries=data.get("max_retries", 3),
            max_verification_attempts=data.get("max_verification_attempts", 2),
            max_runtime_seconds=data.get("max_runtime_seconds", 300),
            max_tokens=data.get("max_tokens", 100_000),
            max_cost=data.get("max_cost", 1.0),
            tool_call_budget=data.get("tool_call_budget", 10),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "max_verification_attempts": self.max_verification_attempts,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_tokens": self.max_tokens,
            "max_cost": self.max_cost,
            "tool_call_budget": self.tool_call_budget,
        }


@dataclass
class BudgetTracker:
    """Tracks consumption against an :class:`ExecutionBudget`.

    Usage::

        tracker = BudgetTracker(budget)
        if tracker.can_retry():
            tracker.consume_retry()
            ... do work ...
    """

    budget: ExecutionBudget
    _retry_count: int = field(default=0, init=False)
    _verification_count: int = field(default=0, init=False)
    _tokens_used: int = field(default=0, init=False)
    _cost_used: float = field(default=0.0, init=False)
    _tool_calls_used: int = field(default=0, init=False)
    _start_time: float | None = field(default=None, init=False)
    _exhausted_reason: str | None = field(default=None, init=False)

    def can_retry(self) -> bool:
        """Check if retries are still available."""
        return self._retry_count < self.budget.max_retries

    def can_verify(self) -> bool:
        """Check if verification attempts are still available."""
        return self._verification_count < self.budget.max_verification_attempts

    def can_use_tool(self) -> bool:
        """Check if tool call budget allows more calls."""
        return self._tool_calls_used < self.budget.tool_call_budget

    def consume_retry(self) -> None:
        """Record a retry attempt."""
        self._retry_count += 1
        if self._retry_count >= self.budget.max_retries:
            self._exhausted_reason = (
                f"Retry budget exhausted: {self._retry_count}/{self.budget.max_retries}"
            )

    def consume_verification(self) -> None:
        """Record a verification attempt."""
        self._verification_count += 1

    def consume_tokens(self, count: int) -> None:
        """Record token usage."""
        self._tokens_used += count
        if self._tokens_used >= self.budget.max_tokens:
            self._exhausted_reason = (
                f"Token budget exhausted: {self._tokens_used}/{self.budget.max_tokens}"
            )

    def consume_cost(self, amount: float) -> None:
        """Record cost usage."""
        self._cost_used += amount
        if self._cost_used >= self.budget.max_cost:
            self._exhausted_reason = (
                f"Cost budget exhausted: ${self._cost_used:.4f}/${self.budget.max_cost:.4f}"
            )

    def consume_tool_call(self) -> None:
        """Record a tool call."""
        self._tool_calls_used += 1

    def exhausted(self) -> bool:
        """Check if any budget is exhausted."""
        return self._exhausted_reason is not None

    def exhausted_reason(self) -> str | None:
        """Return the reason for budget exhaustion."""
        return self._exhausted_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget.to_dict(),
            "retry_count": self._retry_count,
            "verification_count": self._verification_count,
            "tokens_used": self._tokens_used,
            "cost_used": self._cost_used,
            "tool_calls_used": self._tool_calls_used,
            "exhausted": self.exhausted(),
            "exhausted_reason": self._exhausted_reason,
        }
