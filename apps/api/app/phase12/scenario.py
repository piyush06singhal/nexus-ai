"""Scenario engine — the 11 scenario types and their validation.

A scenario is a baseline (simulation + variables + assumptions + horizon) with
optional constraints and expected metrics. Invalid simulations are rejected at
creation time, before any run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.phase12._types import SimScenario
from app.phase12.variables import SimulationVariable, validate_variables


class ScenarioValidationError(ValueError):
    """A scenario is malformed and cannot be run."""


@dataclass
class Scenario:
    """A normalised scenario ready for the engine."""

    name: str
    scenario_type: SimScenario
    simulation_id: UUID
    company_id: UUID | None = None
    description: str | None = None
    assumptions: dict[str, Any] = field(default_factory=dict)
    horizon_days: int | None = None
    variables: list[SimulationVariable] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    objectives: dict[str, Any] = field(default_factory=dict)
    expected_metrics: dict[str, Any] = field(default_factory=dict)
    is_baseline: bool = False


class ScenarioEngine:
    """Validates and normalises scenario definitions into runnable scenarios."""

    SUPPORTED = {
        SimScenario.BASELINE,
        SimScenario.WHAT_IF,
        SimScenario.STRESS_TEST,
        SimScenario.CAPACITY_TEST,
        SimScenario.RESOURCE_TEST,
        SimScenario.STRATEGY_TEST,
        SimScenario.WORKFORCE_TEST,
        SimScenario.AGENT_TEST,
        SimScenario.PRODUCT_TEST,
        SimScenario.RISK_TEST,
        SimScenario.CUSTOM,
    }

    def build(
        self,
        *,
        name: str,
        scenario_type: str | SimScenario,
        simulation_id: UUID,
        company_id: UUID | None = None,
        description: str | None = None,
        assumptions: dict[str, Any] | None = None,
        horizon_days: int | None = None,
        variables: list[SimulationVariable] | None = None,
        constraints: dict[str, Any] | None = None,
        objectives: dict[str, Any] | None = None,
        expected_metrics: dict[str, Any] | None = None,
        is_baseline: bool = False,
    ) -> Scenario:
        kind = SimScenario(scenario_type)
        if kind not in self.SUPPORTED:
            raise ScenarioValidationError(f"Unsupported scenario type: {kind.value}")
        if not name.strip():
            raise ScenarioValidationError("Scenario name is required")
        if horizon_days is not None and not (1 <= horizon_days <= 3650):
            raise ScenarioValidationError("horizon_days must be within 1..3650")
        variables = list(variables or [])
        try:
            validate_variables(variables)
        except ValueError as exc:  # re-raise as a scenario error at the boundary
            raise ScenarioValidationError(str(exc)) from exc
        return Scenario(
            name=name,
            scenario_type=kind,
            simulation_id=simulation_id,
            company_id=company_id,
            description=description,
            assumptions=assumptions or {},
            horizon_days=horizon_days,
            variables=variables,
            constraints=constraints or {},
            objectives=objectives or {},
            expected_metrics=expected_metrics or {},
            is_baseline=is_baseline,
        )
