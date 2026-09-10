"""Resource and policy limits for multi-agent orchestration.

Centralizes every guardrail an orchestration run enforces (spec §27) into one
config-driven bundle so tests and deployments can constrain runaway execution
without scattering limits through the engine.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrchestrationLimits:
    """Bounded resource limits for a single orchestration run."""

    max_agents: int = 20
    max_tasks: int = 50
    max_parallel_agents: int = 5
    max_parallel_tasks: int = 5
    max_execution_duration_seconds: int = 3600
    max_execution_iterations: int = 100
    max_messages: int = 500
    max_review_iterations: int = 3
    token_budget: int | None = None
    cost_budget: float | None = None

    @classmethod
    def from_settings(cls, settings) -> OrchestrationLimits:
        """Build limits from the application :class:`Settings` singleton."""
        return cls(
            max_agents=settings.orchestration_max_agents,
            max_tasks=settings.orchestration_max_tasks,
            max_parallel_agents=settings.orchestration_max_parallel_agents,
            max_parallel_tasks=settings.orchestration_max_parallel_tasks,
            max_execution_duration_seconds=settings.orchestration_max_execution_duration_seconds,
            max_execution_iterations=settings.orchestration_max_execution_iterations,
            max_messages=settings.orchestration_max_messages_per_orchestration,
            max_review_iterations=settings.orchestration_max_review_iterations,
            token_budget=settings.orchestration_token_budget,
            cost_budget=settings.orchestration_cost_budget,
        )
