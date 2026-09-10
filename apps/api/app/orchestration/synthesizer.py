"""Result synthesis (spec §14, §15, §16).

The :class:`ResultSynthesizer` protocol aggregates an orchestration's results
into a single structured final result. :class:`DeterministicSynthesizer` is the
default: it merges every agent's contribution while preserving **source
attribution** (agent/task per finding), carries forward intermediate results,
lists unresolved conflicts and incomplete tasks, and never invents data — the
output is a strict function of the results present (no external model).
"""

from __future__ import annotations

import json

from app.db.models.orchestration import (
    Orchestration,
    OrchestrationResult,
    OrchestrationTask,
    OrchestrationTaskStatus,
)
from app.orchestration.types import SynthesisError


def _loads(raw: str | None):
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


class ResultSynthesizer:
    """Merge an orchestration's results into a structured final result."""

    def __init__(self, *, final_status: str = "completed") -> None:
        self._final_status = final_status

    def synthesize(
        self,
        orchestration: Orchestration,
        results: list[OrchestrationResult],
        tasks: list[OrchestrationTask],
        conflicts: list | None = None,
    ) -> dict:
        """Return the spec's structured final-result shape.

        Raises :class:`SynthesisError` when there are no results at all to
        synthesize (the orchestrator uses this to drive FAILED/partial).
        """
        conflicts = conflicts or []
        if not results:
            raise SynthesisError("No results to synthesize — nothing to aggregate")

        # Findings with source attribution, keyed per result.
        findings: list[dict] = []
        agent_contributions: dict[str, list[str]] = {}
        for result in results:
            data = _loads(result.structured_data)
            agent_key = str(result.agent_id) if result.agent_id else "system"
            agent_contributions.setdefault(agent_key, []).append(str(result.task_id))
            if data:
                findings.append(
                    {
                        "task_id": str(result.task_id) if result.task_id else None,
                        "agent_id": agent_key,
                        "summary": (result.content or "")[:400],
                        "data": data,
                        "confidence": result.confidence,
                    }
                )

        incomplete = [
            {
                "task_id": str(t.id),
                "name": t.name,
                "status": t.status.value,
            }
            for t in tasks
            if t.status not in (OrchestrationTaskStatus.COMPLETED, OrchestrationTaskStatus.SKIPPED)
        ]

        # A short deterministic summary: the objective plus per-agent result
        # headlines. Never consults a model.
        task_name_by_id = {str(t.id): t.name for t in tasks}
        summaries = []
        for agent_key in sorted(agent_contributions):
            summaries.append(
                f"agent {agent_key}: {len(agent_contributions[agent_key])} contribution(s)"
            )
        summary = (
            f"Executed objective {orchestration.objective!r}: "
            + "; ".join(summaries)
            + (f"; {len(conflicts)} unresolved conflict(s)" if conflicts else "")
        )

        return {
            "status": self._final_status,
            "summary": summary,
            "findings": findings,
            "sources": [
                {
                    "task_id": str(r.task_id) if r.task_id else None,
                    "agent_id": str(r.agent_id) if r.agent_id else None,
                    "task_name": task_name_by_id.get(str(r.task_id)),
                    "content": (r.content or "")[:400],
                    "confidence": r.confidence,
                }
                for r in results
            ],
            "conflicts": [
                {
                    "field": c.field,
                    "agent_a": str(c.agent_a) if c.agent_a else None,
                    "agent_b": str(c.agent_b) if c.agent_b else None,
                    "value_a": c.value_a,
                    "value_b": c.value_b,
                    "kind": c.kind,
                }
                for c in conflicts
            ],
            "incomplete_tasks": incomplete,
            "agent_contributions": agent_contributions,
        }


def build_source_attribution(results: list[OrchestrationResult]) -> list[dict]:
    """Return a denormalized source-attribution list for the UI/timeline."""
    return [
        {
            "task_id": str(r.task_id) if r.task_id else None,
            "agent_id": str(r.agent_id) if r.agent_id else None,
            "content": (r.content or "")[:400],
            "confidence": r.confidence,
        }
        for r in results
    ]


def result_to_structured(result: OrchestrationResult) -> dict:
    """Safe accessor for a result's structured data (used by the synthesizer)."""
    return _loads(result.structured_data)
