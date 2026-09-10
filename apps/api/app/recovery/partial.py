"""Partial completion builder (Phase 6, spec §23).

Aggregates completed, failed, and skipped work into a
``PARTIALLY_COMPLETED`` record when full recovery is not possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PartialCompletion:
    """Record of partial completion when full recovery is impossible."""

    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    confidence: float = 0.0
    remaining_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed": self.completed,
            "failed": self.failed,
            "missing": self.missing,
            "confidence": self.confidence,
            "remaining_actions": self.remaining_actions,
        }


class PartialCompletionBuilder:
    """Aggregates completed/failed/skipped work into a partial record (§23)."""

    def build(
        self,
        completed_tasks: list[str] | None = None,
        failed_tasks: list[str] | None = None,
        skipped_tasks: list[str] | None = None,
        total_tasks: int = 0,
    ) -> PartialCompletion:
        """Build a partial completion record.

        Args:
            completed_tasks: Names/IDs of completed tasks.
            failed_tasks: Names/IDs of failed tasks.
            skipped_tasks: Names/IDs of skipped tasks.
            total_tasks: Total number of tasks in the workflow.

        Returns:
            A :class:`PartialCompletion` record.
        """
        completed = completed_tasks or []
        failed = failed_tasks or []
        skipped = skipped_tasks or []

        # Confidence = completed / total
        confidence = len(completed) / max(total_tasks, 1)

        # Missing = tasks that are neither completed nor failed nor skipped
        known = set(completed + failed + skipped)
        missing = [f"task_{i}" for i in range(total_tasks) if f"task_{i}" not in known]

        # Remaining actions = what needs to be done to complete
        remaining = list(failed + missing)

        return PartialCompletion(
            completed=completed,
            failed=failed,
            missing=missing,
            confidence=round(confidence, 4),
            remaining_actions=remaining,
        )
