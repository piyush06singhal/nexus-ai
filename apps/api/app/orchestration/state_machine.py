"""Orchestration state machine.

Enforces legal lifecycle transitions for orchestrations, tasks, and agent
assignments. Invalid transitions raise :class:`InvalidTransitionError` so no
status can silently drift into an inconsistent state (spec §17).
"""

from __future__ import annotations

from app.db.models.orchestration import (
    AssignmentStatus,
    OrchestrationStatus,
    OrchestrationTaskStatus,
)
from app.orchestration.types import InvalidTransitionError

# Orchestration lifecycle.
# Normal path: created → planning → planned → assigning → running →
#              synthesizing → completed.
# Failure/partial/cancel: running → failed | partially_completed | cancelled.
_ORCHESTRATION_TRANSITIONS: dict[OrchestrationStatus, set[OrchestrationStatus]] = {
    OrchestrationStatus.CREATED: {OrchestrationStatus.PLANNING, OrchestrationStatus.CANCELLED},
    OrchestrationStatus.PLANNING: {OrchestrationStatus.PLANNED, OrchestrationStatus.FAILED},
    OrchestrationStatus.PLANNED: {OrchestrationStatus.ASSIGNING, OrchestrationStatus.FAILED},
    OrchestrationStatus.ASSIGNING: {OrchestrationStatus.RUNNING, OrchestrationStatus.FAILED},
    OrchestrationStatus.RUNNING: {
        OrchestrationStatus.SYNTHESIZING,
        OrchestrationStatus.FAILED,
        OrchestrationStatus.PARTIALLY_COMPLETED,
        OrchestrationStatus.CANCELLED,
    },
    OrchestrationStatus.SYNTHESIZING: {
        OrchestrationStatus.COMPLETED,
        OrchestrationStatus.PARTIALLY_COMPLETED,
        OrchestrationStatus.FAILED,
    },
    OrchestrationStatus.COMPLETED: set(),
    OrchestrationStatus.PARTIALLY_COMPLETED: set(),
    OrchestrationStatus.FAILED: set(),
    OrchestrationStatus.CANCELLED: set(),
}

# Task lifecycle.
_TASK_TRANSITIONS: dict[OrchestrationTaskStatus, set[OrchestrationTaskStatus]] = {
    OrchestrationTaskStatus.PENDING: {
        OrchestrationTaskStatus.READY,
        OrchestrationTaskStatus.SKIPPED,
        OrchestrationTaskStatus.CANCELLED,
        OrchestrationTaskStatus.FAILED,
    },
    OrchestrationTaskStatus.READY: {
        OrchestrationTaskStatus.RUNNING,
        OrchestrationTaskStatus.SKIPPED,
        OrchestrationTaskStatus.CANCELLED,
    },
    OrchestrationTaskStatus.RUNNING: {
        OrchestrationTaskStatus.COMPLETED,
        OrchestrationTaskStatus.FAILED,
        OrchestrationTaskStatus.SKIPPED,
        OrchestrationTaskStatus.CANCELLED,
    },
    OrchestrationTaskStatus.COMPLETED: set(),
    OrchestrationTaskStatus.FAILED: set(),
    OrchestrationTaskStatus.SKIPPED: set(),
    OrchestrationTaskStatus.CANCELLED: set(),
}

# Assignment lifecycle.
_ASSIGNMENT_TRANSITIONS: dict[AssignmentStatus, set[AssignmentStatus]] = {
    AssignmentStatus.PENDING: {
        AssignmentStatus.ASSIGNED,
        AssignmentStatus.CANCELLED,
    },
    AssignmentStatus.ASSIGNED: {
        AssignmentStatus.RUNNING,
        AssignmentStatus.CANCELLED,
        AssignmentStatus.FAILED,
    },
    AssignmentStatus.RUNNING: {
        AssignmentStatus.COMPLETED,
        AssignmentStatus.FAILED,
        AssignmentStatus.CANCELLED,
        AssignmentStatus.TIMED_OUT,
    },
    AssignmentStatus.COMPLETED: set(),
    AssignmentStatus.FAILED: set(),
    AssignmentStatus.CANCELLED: set(),
    AssignmentStatus.TIMED_OUT: set(),
}


def orchestration_can_transition(
    current: OrchestrationStatus, next_status: OrchestrationStatus
) -> bool:
    """Return whether *current* may transition to *next_status*."""
    return next_status in _ORCHESTRATION_TRANSITIONS.get(current, set())


def task_can_transition(
    current: OrchestrationTaskStatus, next_status: OrchestrationTaskStatus
) -> bool:
    """Return whether a task may transition between the two statuses."""
    return next_status in _TASK_TRANSITIONS.get(current, set())


def assignment_can_transition(current: AssignmentStatus, next_status: AssignmentStatus) -> bool:
    """Return whether an assignment may transition between the two statuses."""
    return next_status in _ASSIGNMENT_TRANSITIONS.get(current, set())


def transition_orchestration(
    current: OrchestrationStatus, next_status: OrchestrationStatus
) -> OrchestrationStatus:
    """Validate and perform an orchestration status transition."""
    if not orchestration_can_transition(current, next_status):
        raise InvalidTransitionError(
            f"Illegal orchestration transition: {current.value!r} → {next_status.value!r}"
        )
    return next_status


def transition_task(
    current: OrchestrationTaskStatus, next_status: OrchestrationTaskStatus
) -> OrchestrationTaskStatus:
    """Validate and perform a task status transition."""
    if not task_can_transition(current, next_status):
        raise InvalidTransitionError(
            f"Illegal task transition: {current.value!r} → {next_status.value!r}"
        )
    return next_status


def transition_assignment(
    current: AssignmentStatus, next_status: AssignmentStatus
) -> AssignmentStatus:
    """Validate and perform an assignment status transition."""
    if not assignment_can_transition(current, next_status):
        raise InvalidTransitionError(
            f"Illegal assignment transition: {current.value!r} → {next_status.value!r}"
        )
    return next_status
