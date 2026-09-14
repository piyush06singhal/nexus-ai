"""Tests for the orchestration state machine (spec §17, §33)."""

from __future__ import annotations

import pytest

from app.db.models.orchestration import (
    AssignmentStatus,
    OrchestrationStatus,
    OrchestrationTaskStatus,
)
from app.orchestration.state_machine import (
    assignment_can_transition,
    orchestration_can_transition,
    task_can_transition,
    transition_assignment,
    transition_orchestration,
    transition_task,
)
from app.orchestration.types import InvalidTransitionError

# ── Orchestration transitions ────────────────────────────────────────────────


def test_created_to_planning_is_valid():
    assert orchestration_can_transition(OrchestrationStatus.CREATED, OrchestrationStatus.PLANNING)


def test_normal_lifecycle_path_is_valid():
    transitions = [
        (OrchestrationStatus.CREATED, OrchestrationStatus.PLANNING),
        (OrchestrationStatus.PLANNING, OrchestrationStatus.PLANNED),
        (OrchestrationStatus.PLANNED, OrchestrationStatus.ASSIGNING),
        (OrchestrationStatus.ASSIGNING, OrchestrationStatus.RUNNING),
        (OrchestrationStatus.RUNNING, OrchestrationStatus.SYNTHESIZING),
        (OrchestrationStatus.SYNTHESIZING, OrchestrationStatus.COMPLETED),
    ]
    for current, nxt in transitions:
        assert orchestration_can_transition(current, nxt)
        assert transition_orchestration(current, nxt) == nxt


def test_claimed_running_rewinds_to_planning():
    # OrchestrationWorker claims a CREATED row by moving it to RUNNING, then
    # hands it to Orchestrator.execute which begins machine execution at
    # PLANNING. That re-entry must be a legal edge (regression: it was not,
    # so any worker-drained run died with an Illegal transition error).
    assert orchestration_can_transition(OrchestrationStatus.RUNNING, OrchestrationStatus.PLANNING)
    assert (
        transition_orchestration(OrchestrationStatus.RUNNING, OrchestrationStatus.PLANNING)
        == OrchestrationStatus.PLANNING
    )


def test_running_to_terminal_statuses():
    assert orchestration_can_transition(OrchestrationStatus.RUNNING, OrchestrationStatus.FAILED)
    assert orchestration_can_transition(
        OrchestrationStatus.RUNNING, OrchestrationStatus.PARTIALLY_COMPLETED
    )
    assert orchestration_can_transition(OrchestrationStatus.RUNNING, OrchestrationStatus.CANCELLED)


def test_skipping_planning_stage_is_rejected():
    assert not orchestration_can_transition(
        OrchestrationStatus.CREATED, OrchestrationStatus.PLANNED
    )


def test_terminal_status_has_no_outgoing_edges():
    assert not orchestration_can_transition(
        OrchestrationStatus.COMPLETED, OrchestrationStatus.RUNNING
    )
    assert not orchestration_can_transition(OrchestrationStatus.FAILED, OrchestrationStatus.RUNNING)
    assert not orchestration_can_transition(
        OrchestrationStatus.CANCELLED, OrchestrationStatus.RUNNING
    )


def test_invalid_transition_raises():
    with pytest.raises(InvalidTransitionError):
        transition_orchestration(OrchestrationStatus.CREATED, OrchestrationStatus.SYNTHESIZING)


def test_created_to_cancelled():
    assert (
        transition_orchestration(OrchestrationStatus.CREATED, OrchestrationStatus.CANCELLED)
        == OrchestrationStatus.CANCELLED
    )


# ── Task transitions ──────────────────────────────────────────────────────────


def test_task_lifecycle_valid():
    assert (
        transition_task(OrchestrationTaskStatus.PENDING, OrchestrationTaskStatus.READY)
        == OrchestrationTaskStatus.READY
    )
    assert (
        transition_task(OrchestrationTaskStatus.READY, OrchestrationTaskStatus.RUNNING)
        == OrchestrationTaskStatus.RUNNING
    )
    assert (
        transition_task(OrchestrationTaskStatus.RUNNING, OrchestrationTaskStatus.COMPLETED)
        == OrchestrationTaskStatus.COMPLETED
    )


def test_task_cannot_skip_ready():
    assert not task_can_transition(OrchestrationTaskStatus.PENDING, OrchestrationTaskStatus.RUNNING)


def test_completed_task_is_terminal():
    assert not task_can_transition(
        OrchestrationTaskStatus.COMPLETED, OrchestrationTaskStatus.PENDING
    )


def test_failed_dependency_skips_dependent():
    assert task_can_transition(OrchestrationTaskStatus.PENDING, OrchestrationTaskStatus.SKIPPED)


@pytest.mark.parametrize(
    "current,nxt",
    [
        (OrchestrationTaskStatus.PENDING, OrchestrationTaskStatus.RUNNING),
        (OrchestrationTaskStatus.COMPLETED, OrchestrationTaskStatus.RUNNING),
    ],
)
def test_invalid_task_transitions_raise(current, nxt):
    with pytest.raises(InvalidTransitionError):
        transition_task(current, nxt)


# ── Assignment transitions ────────────────────────────────────────────────────


def test_assignment_lifecycle_valid():
    assert (
        transition_assignment(AssignmentStatus.PENDING, AssignmentStatus.ASSIGNED)
        == AssignmentStatus.ASSIGNED
    )
    assert (
        transition_assignment(AssignmentStatus.ASSIGNED, AssignmentStatus.RUNNING)
        == AssignmentStatus.RUNNING
    )
    assert (
        transition_assignment(AssignmentStatus.RUNNING, AssignmentStatus.COMPLETED)
        == AssignmentStatus.COMPLETED
    )


def test_running_can_time_out_or_fail():
    assert assignment_can_transition(AssignmentStatus.RUNNING, AssignmentStatus.TIMED_OUT)
    assert assignment_can_transition(AssignmentStatus.RUNNING, AssignmentStatus.FAILED)


def test_invalid_assignment_transition_raises():
    with pytest.raises(InvalidTransitionError):
        transition_assignment(AssignmentStatus.PENDING, AssignmentStatus.COMPLETED)
