"""Behavior models — how agents/tasks behave inside a simulation.

Deterministic by default (no randomness), with optional seeded stochasticity so
Monte-Carlo-style multi-runs can vary results without losing reproducibility.
Every run records the behavior model name + version for review.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any  # noqa: F401


@dataclass
class AgentBehaviorModel:
    """Configurable behavior for simulated agents.

    All values are *modeled assumptions* the simulation author sets; they are
    inputs, not measurements. The models converge on deterministic default
    values and only vary when a seed is supplied.
    """

    name: str = "nexus-v1-default"
    version: str = "1.0"
    base_task_latency_ticks: int = 2
    completion_probability: float = 0.95
    failure_probability_offset: float = 0.0
    cost_per_task: float = 0.02  # modeled currency units
    quality_score: float = 0.9
    utilization: float = 0.8  # fraction of capacity a healthy agent supplies
    seed: str | None = None
    _rng: random.Random = field(default_factory=random.Random, repr=False)

    def __post_init__(self) -> None:
        if self.seed is not None:
            self._rng.seed(self.seed)

    @property
    def stochastic(self) -> bool:
        return self.seed is not None

    def completion_proba(self) -> float:
        if not self.stochastic:
            return self.completion_probability
        lo = max(0.0, self.completion_probability - 0.05)
        hi = min(1.0, self.completion_probability + 0.05)
        return self._rng.uniform(lo, hi)

    def latency_ticks(self) -> int:
        if not self.stochastic:
            return self.base_task_latency_ticks
        return max(1, self.base_task_latency_ticks + self._rng.randint(0, 1))

    def failed(self) -> bool:
        p = max(0.0, min(1.0, self.completion_probability + self.failure_probability_offset))
        if not self.stochastic:
            return False
        return self._rng.random() > p


class TaskCompletionModel:
    """Scores whether a simulated task completes given agent behavior."""

    def complete(self, behavior: AgentBehaviorModel, *, failure_weight: float = 1.0) -> bool:
        if behavior.stochastic:
            return not behavior.failed()
        p = behavior.completion_probability + behavior.failure_probability_offset
        return p >= 0.5


class FailureProbabilityModel:
    def probability(self, behavior: AgentBehaviorModel) -> float:
        return max(0.0, 1.0 - behavior.completion_proba())


class LatencyModel:
    def ticks(self, behavior: AgentBehaviorModel, *, task_complexity: float = 1.0) -> int:
        return max(1, round(behavior.latency_ticks() * max(0.1, task_complexity)))


class CostModel:
    def cost(self, behavior: AgentBehaviorModel, *, task_complexity: float = 1.0) -> float:
        return round(behavior.cost_per_task * max(0.1, task_complexity), 6)


class QualityModel:
    def quality(self, behavior: AgentBehaviorModel) -> float:
        return behavior.quality_score
