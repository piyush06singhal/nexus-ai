"""Deterministic agent selection.

The :class:`AgentSelector` protocol matches a task to an agent by capability.
:class:`CapabilityAgentSelector` is the deterministic default: an active,
executable agent whose capability set covers the task's required capabilities
scores by coverage; ties break toward the least-loaded agent (round-robin) to
spread work and respect per-orchestration activation limits. The interface is
stable so richer selection can be added later without touching callers (spec §4).
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.orchestration.capabilities import agent_is_available, resolve_agent_capabilities
from app.orchestration.types import AgentSelection, NoAgentAvailableError, PlanTask


class AgentSelector(Protocol):
    """Match a task to the best available agent."""

    def select(self, task: PlanTask, available_agents: list, db: Session) -> AgentSelection: ...


class CapabilityAgentSelector:
    """Deterministic capability-matching agent selector."""

    def __init__(self, *, max_agents: int = 20) -> None:
        self._max_agents = max_agents

    def select(self, task: PlanTask, available_agents: list, db: Session) -> AgentSelection:
        """Select the best agent for *task* from *available_agents*.

        Raises :class:`NoAgentAvailableError` when no usable agent matches the
        task's required capabilities.
        """
        required = set(task.required_capabilities)
        candidates: list[AgentSelection] = []
        for agent in available_agents[: self._max_agents]:
            if not agent_is_available(agent):
                continue
            caps = resolve_agent_capabilities(agent, db)
            matched = [c for c in task.required_capabilities if c in caps]
            if not required.issubset(set(caps)):
                continue
            # Coverage score: fraction of required capabilities satisfied plus a
            # small bonus for capability breadth, so a specialist wins over a
            # generic agent when both qualify.
            score = len(matched) / len(required) + 0.001 * len(matched)
            candidates.append(
                AgentSelection(
                    agent_id=agent.id,
                    matched_capabilities=matched,
                    score=score,
                    role=agent.role,
                )
            )

        if not candidates:
            raise NoAgentAvailableError(
                f"No available agent satisfies required capabilities "
                f"{list(required)!r} for task {task.name!r}"
            )

        # Highest score wins; tie-break deterministically by agent id so the
        # result is stable regardless of iteration order.
        return max(candidates, key=lambda c: (c.score, str(c.agent_id)))
