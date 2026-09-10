"""Execution planning / task decomposition.

The :class:`Planner` abstraction turns an objective into a validated
:class:`ExecutionPlan` (tasks with required capabilities and explicit
dependencies). The :class:`DeterministicPlanner` ships a rule-based producer so
planning works without any API call — the market-research template matches the
Phase 5 deterministic demo, with a generic single-task fallback. The interface
is stable so a model-backed planner can be swapped in later without changing
callers (spec §5, §6).
"""

from __future__ import annotations

import re
from typing import Protocol

from app.orchestration.capabilities import (
    ANALYSIS,
    FACT_CHECKING,
    GENERAL,
    RESEARCH,
    WRITING,
)
from app.orchestration.types import ExecutionPlan, PlannerError, PlanTask


class Planner(Protocol):
    """Produce a validated execution plan for an objective."""

    def create_plan(
        self, objective: str, available_agents: list, context: dict
    ) -> ExecutionPlan: ...


def _has_cycle(edges: dict[str, set[str]]) -> bool:
    """Detect a cycle in a dependency graph (reuses the workflow validator's
    algorithm so plan validation matches established semantics)."""
    visited: set[str] = set()
    in_stack: set[str] = set()

    def dfs(node: str) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for dep in edges.get(node, set()):
            if dep not in edges:
                continue
            if dfs(dep):
                return True
        in_stack.discard(node)
        return False

    return any(dfs(name) for name in edges)


def validate_plan(plan: ExecutionPlan) -> None:
    """Validate a plan's task graph; raise :class:`PlannerError` if invalid.

    Rejects: empty/malformed tasks, self or dangling dependencies, and cycles
    (spec §33 planning tests). This runs *before* any assignment or execution.
    """
    if not plan.tasks:
        raise PlannerError("Execution plan is empty — nothing to execute")
    if not plan.objective or not plan.objective.strip():
        raise PlannerError("Execution plan has no objective")

    names: set[str] = {t.name for t in plan.tasks}
    if len(names) != len(plan.tasks):
        raise PlannerError("Execution plan has duplicate task names")

    edges: dict[str, set[str]] = {}
    for task in plan.tasks:
        if not task.name:
            raise PlannerError("Execution plan has a task with no name")
        deps = set(task.dependencies)
        if task.name in deps:
            raise PlannerError(f"Task {task.name!r} depends on itself")
        for dep in deps:
            if dep not in names:
                raise PlannerError(f"Task {task.name!r} references unknown dependency {dep!r}")
        edges[task.name] = deps

    if _has_cycle(edges):
        raise PlannerError("Execution plan has a circular dependency")


# Templates keyed by a normalized objective slug. First matching template whose
# required trigger appears in the objective wins.
# (description, required_capabilities, dependencies)
_MARKET_TEMPLATE: list[tuple[str, str, list[str], list[str]]] = [
    (
        "research",
        "Research the market, competitors, and technology landscape.",
        [RESEARCH],
        [],
    ),
    (
        "analysis",
        "Analyze market trends, pricing, and competitive positioning.",
        [ANALYSIS],
        [],
    ),
    (
        "fact_checking",
        "Verify the research against known facts and flag uncertainties.",
        [FACT_CHECKING],
        [],
    ),
    (
        "writing",
        "Synthesize the findings into a structured competitive analysis report.",
        [WRITING],
        [RESEARCH, ANALYSIS, FACT_CHECKING],
    ),
]

_MARKET_TRIGGERS = re.compile(
    r"\b(market|competitive|competitor|report|analysis|industry)\b", re.IGNORECASE
)

_GENERIC_TASKS = [
    PlanTask(
        name="complete",
        description="Work toward the objective using general reasoning and tools.",
        required_capabilities=[GENERAL],
        dependencies=[],
    ),
]


class DeterministicPlanner:
    """A rule-based planner producing validated structured decompositions."""

    def create_plan(self, objective: str, available_agents: list, context: dict) -> ExecutionPlan:
        """Return a deterministic :class:`ExecutionPlan` for *objective*.

        ``available_agents`` and ``context`` are accepted for interface parity
        with a future model-backed planner; the deterministic producer keys
        only on the objective text.
        """
        objective = objective.strip()
        tasks = self._decompose(objective)
        plan = ExecutionPlan(objective=objective, tasks=tasks, strategy="deterministic")
        validate_plan(plan)
        return plan

    def _decompose(self, objective: str) -> list[PlanTask]:
        if _MARKET_TRIGGERS.search(objective):
            return [
                PlanTask(
                    name=name,
                    description=description,
                    required_capabilities=required_capabilities,
                    dependencies=dependencies,
                )
                for name, description, required_capabilities, dependencies in _MARKET_TEMPLATE
            ]
        return [PlanTask(**task.__dict__) for task in _GENERIC_TASKS]
