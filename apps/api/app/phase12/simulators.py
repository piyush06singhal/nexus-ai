"""Simulators — the modeled engines that project behavior inside a run.

- ``WorkforceSimulator``: capacity / utilization / availability / assignment /
  bottleneck / hiring projections.
- ``BudgetSimulator``: projected spend, remaining, utilization, cost/task,
  cost/successful outcome, cost variance. Respects Phase 11 resource limits
  when a ``ResourceGovernanceService`` is supplied (passed as a callable that
  checks a category+amount, so the sim layer stays decoupled).
- ``KpiSimulator``: simulates KPI *definitions* forward — never overwrites
  ACTUAL ``KpiValue`` rows; outputs labeled ACTUAL/SIMULATED/FORECAST.
- ``RiskSimulator``: operational / capacity / execution / dependency / budget /
  reliability / security / project risk estimates + stress scenarios (no real
  attacks ever executed).

All values are modeled estimates — never predictions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.phase12.behavior import AgentBehaviorModel


@dataclass
class WorkforceSimulator:
    """Project workforce capacity/utilization given headcount and behavior."""

    headcount: int = 5
    capacity_per_employee: float = 1.0  # units of work per tick
    behavior: AgentBehaviorModel = field(default_factory=AgentBehaviorModel)

    def total_capacity(self) -> float:
        return self.headcount * self.capacity_per_employee * self.behavior.utilization

    def utilization(self, work_units: float) -> float:
        cap = self.total_capacity()
        if cap <= 0:
            return 0.0
        return round(min(1.0, work_units / cap), 4)

    def projected_surplus(self, work_units: float) -> float:
        """Bottleneck signal: positive = idle capacity, negative = overload."""
        return round(self.total_capacity() - work_units, 4)

    def hiring_needed(self, work_units: float) -> int:
        """Headcount to avoid overload for a given work load."""
        cap = self.total_capacity()
        if cap >= work_units or cap <= 0:
            return 0
        per_employee = self.capacity_per_employee * self.behavior.utilization
        return max(1, int((work_units - cap) / per_employee) + 1)

    def availability(self, *, unavailable: int = 0) -> float:
        active = max(0, self.headcount - unavailable)
        return round(active / self.headcount, 4) if self.headcount else 0.0

    def to_public(self) -> dict[str, Any]:
        return {
            "headcount": self.headcount,
            "capacity_per_employee": self.capacity_per_employee,
            "total_capacity": self.total_capacity(),
            "utilization_behavior": self.behavior.utilization,
        }


@dataclass
class BudgetSimulator:
    """Project budget spend forward for a work plan under a resource limit."""

    budget: float = 1000.0
    spent: float = 0.0
    behavior: AgentBehaviorModel = field(default_factory=AgentBehaviorModel)
    # Optional governance check: callable(category, amount) -> allowed: bool,
    # so the simulator respects Phase 11 ResourceGovernanceService without
    # hard-coupling to it.
    resource_check: Callable[[str, float], bool] | None = None

    def remaining(self) -> float:
        return round(self.budget - self.spent, 4)

    def projected_spend(self, task_count: int, *, complexity: float = 1.0) -> float:
        per = self.behavior.cost_per_task * max(0.1, complexity)
        projected = task_count * per
        if self.resource_check is not None and not self.resource_check("cost", projected):
            projected = self.budget - self.spent  # capped by the limit
        return round(projected, 6)

    def utilization(self) -> float:
        if self.budget <= 0:
            return 0.0
        return round(min(1.0, (self.spent / self.budget)), 4)

    def cost_per_task(self, task_count: int) -> float:
        if task_count <= 0:
            return 0.0
        return round(self.behavior.cost_per_task, 6)

    def cost_per_success(self, task_count: int, completed: int) -> float:
        if completed <= 0:
            return 0.0
        return round((self.spent / completed), 6)

    def cost_variance(self, current: float) -> float:
        """variance of modeled cost vs the plan; positive = overrun."""
        per_task = max(0.0001, self.behavior.cost_per_task)
        return round(current - self.projected_spend(round(current / per_task)), 6)

    def to_public(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "spent": self.spent,
            "remaining": self.remaining(),
            "utilization": self.utilization(),
        }


@dataclass
class KpiSimulator:
    """Simulate a KPI forward from its definition + a modeled trajectory.

    Reads KPI *definitions* (from Phase 8) but never writes to ``kpi_values``.
    Output kind is always SIMULATED/FORECAST, never ACTUAL.
    """

    baseline_values: dict[str, float] = field(default_factory=dict)
    unit: str | None = None

    def forecast(
        self, key: str, *, growth_rate: float = 0.0, horizon_ticks: int = 1
    ) -> list[float]:
        base = self.baseline_values.get(key, 0.0)
        out: list[float] = []
        v = base
        for _ in range(horizon_ticks):
            v = v * (1.0 + growth_rate)
            out.append(round(v, 4))
        return out

    def output_kind(self) -> str:
        return "forecast"


@dataclass
class RiskSimulator:
    """Estimate risk scores across dimensions. Stress scenarios are internal
    modeled projections — no real system is ever attacked or stressed."""

    operational: float = 0.1
    capacity: float = 0.2
    execution: float = 0.15
    dependency: float = 0.25
    budget: float = 0.2
    reliability: float = 0.12
    security: float = 0.1
    project: float = 0.18

    _dimension_keys = (
        "operational",
        "capacity",
        "execution",
        "dependency",
        "budget",
        "reliability",
        "security",
        "project",
    )

    def assess(self) -> dict[str, float]:
        return {k: getattr(self, k, 0.0) for k in self._dimension_keys}

    def score(self) -> float:
        values = self.assess()
        if not values:
            return 0.0
        return round(sum(values.values()) / len(values), 4)

    def stress(self, *, factor: float = 1.5) -> dict[str, float]:
        """A modeled stress scenario: scale every dimension by ``factor``."""
        return {k: round(min(1.0, v * factor), 4) for k, v in self.assess().items()}

    def critical_risk(self, threshold: float = 0.5) -> list[str]:
        return [k for k, v in self.assess().items() if v >= threshold]
