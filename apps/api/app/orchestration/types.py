"""Core domain types and structured exceptions for multi-agent orchestration.

Small dataclasses model the planner output (:class:`ExecutionPlan`),
agent selection (:class:`AgentSelection`), and conflict detection
(:class:`Conflict`). Structured exceptions keep failure handling explicit and
testable — every failure surfaces as a typed ``OrchestrationError`` subclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

# ── Exceptions ───────────────────────────────────────────────────────────────


class OrchestrationError(Exception):
    """Base class for all orchestration failures."""


class PlannerError(OrchestrationError):
    """A planner failed to produce a valid execution plan."""


class NoAgentAvailableError(OrchestrationError):
    """No active agent matches a task's required capabilities."""


class InvalidTransitionError(OrchestrationError):
    """A status transition violates the orchestration state machine."""


class AssignmentExecutionError(OrchestrationError):
    """An agent assignment failed to execute (after any configured retries)."""


class SynthesisError(OrchestrationError):
    """Result synthesis could not produce a valid final result."""


class ConflictDetectionError(OrchestrationError):
    """Conflict detection failed unexpectedly."""


class CommunicationError(OrchestrationError):
    """A message could not be delivered or persisted on the agent bus."""


# ── Planner output ───────────────────────────────────────────────────────────


@dataclass
class PlanTask:
    """A single task in an orchestration's execution plan."""

    name: str
    description: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    """Validated, structured decomposition of an objective into tasks."""

    objective: str
    tasks: list[PlanTask]
    strategy: str = "deterministic"


# ── Agent selection ──────────────────────────────────────────────────────────


@dataclass
class AgentSelection:
    """The outcome of matching a task to an agent."""

    agent_id: UUID
    matched_capabilities: list[str]
    score: float
    role: str | None = None


# ── Conflict detection ───────────────────────────────────────────────────────


@dataclass
class Conflict:
    """Two agents reported conflicting values for the same field."""

    field: str
    agent_a: UUID | None
    value_a: object
    agent_b: UUID | None
    value_b: object
    kind: str = "numeric"  # "numeric" | "boolean" | "status" | "unknown"
