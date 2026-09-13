"""Simulation events — the catalog of events that can occur inside a simulation.

Events live inside the simulation only; they never trigger production actions.
Each event carries a kind (from the model enum), a tick, an entity reference,
and structured detail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SimEvent:
    tick: int
    kind: str
    entity_ref: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # info | warning | critical (within the sim only)

    def to_public(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "kind": self.kind,
            "entity_ref": self.entity_ref,
            "detail": self.detail,
            "severity": self.severity,
        }


# Event kinds (must match the model enum SimEventKind values).
class SimEventKind:
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    EMPLOYEE_UNAVAILABLE = "employee_unavailable"
    EMPLOYEE_OVERLOADED = "employee_overloaded"
    AGENT_FAILURE = "agent_failure"
    BUDGET_CHANGE = "budget_change"
    PROJECT_DELAY = "project_delay"
    PRODUCT_LAUNCH = "product_launch"
    KPI_THRESHOLD = "kpi_threshold"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    WORKFLOW_FAILURE = "workflow_failure"
    DEPARTMENT_CHANGE = "department_change"
    PRIORITY_CHANGE = "priority_change"
    # Sandbox boundary: a behavior attempted a production/external side effect
    # (HTTP, email, financial transaction, real DB mutation). The simulation
    # refuses it — the run is marked FAILED and the refusal is recorded.
    SANDBOX_REFUSAL = "sandbox_refusal"


class SimulationEventLog:
    """An append-only in-run event log."""

    def __init__(self) -> None:
        self._events: list[SimEvent] = []

    def record(self, event: SimEvent) -> SimEvent:
        self._events.append(event)
        return event

    def all(self, *, limit: int | None = None) -> list[SimEvent]:
        events = list(self._events)
        if limit is not None:
            events = events[-limit:]
        return events

    def count(self) -> int:
        return len(self._events)
