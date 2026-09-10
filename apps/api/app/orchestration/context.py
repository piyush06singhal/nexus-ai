"""Selective orchestration context construction.

Agents must receive only the context relevant to their task, not the entire
orchestration state (spec §9). :func:`build_assignment_context` composes a
compact input dict from the objective, the task description, shared facts,
decisions, constraints, and — for dependent tasks — the relevant prior task
outputs. Shared context is also mirrored into the Phase 4 Memory system so
agents can retrieve it via the existing runtime hook (spec §9, §10).
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.orchestration import (
    Orchestration,
    OrchestrationContext,
    OrchestrationResult,
    OrchestrationTask,
)


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def build_assignment_context(
    orchestration: Orchestration,
    task: OrchestrationTask,
    completed_results: list[OrchestrationResult] | None = None,
    db: Session | None = None,
) -> dict:
    """Return a task-appropriate context dict for the assigned agent.

    Contains:
    - ``objective``: the top-level objective string
    - ``task``: {name, description}
    - ``shared_context``: relevant facts/decisions/constraints from
      ``orchestration_context``
    - ``prior_results``: structured outputs from completed dependency tasks
      (only when the task has dependencies)

    This is a **subset** of the full orchestration state — no giant state
    blobs are copied into every agent.
    """
    context: dict = {
        "objective": orchestration.objective,
        "task": {"name": task.name, "description": task.description or ""},
        "shared_context": {},
        "prior_results": {},
    }

    # Load shared facts/decisions/constraints.
    if db is not None:
        shared = (
            db.query(OrchestrationContext)
            .filter(OrchestrationContext.orchestration_id == orchestration.id)
            .filter(OrchestrationContext.agent_id.is_(None))  # shared only
            .all()
        )
        for entry in shared:
            context["shared_context"][entry.key] = _loads(entry.value)

    # If this task has dependencies, include their outputs.
    deps = _loads(task.dependencies) or []
    if deps and completed_results:
        result_map = {str(r.task_id): r for r in completed_results if r.task_id}
        for dep_name in deps:
            # Find the task ID for this dependency name.
            dep_task = (
                db.query(OrchestrationTask)
                .filter(OrchestrationTask.orchestration_id == orchestration.id)
                .filter(OrchestrationTask.name == dep_name)
                .first()
            )
            if dep_task and str(dep_task.id) in result_map:
                res = result_map[str(dep_task.id)]
                context["prior_results"][dep_name] = _loads(res.structured_data)

    return context


def upsert_shared_context(
    db: Session,
    orchestration_id: UUID,
    key: str,
    value: object,
    kind: str = "shared_fact",
    agent_id: UUID | None = None,
) -> OrchestrationContext:
    """Create or update a shared (or agent-private) context entry.

    ``agent_id=None`` → shared across all agents in the orchestration.
    ``agent_id=X`` → private to that agent (only that agent sees it in
    ``build_assignment_context`` when filtered).
    """
    existing = (
        db.query(OrchestrationContext)
        .filter(OrchestrationContext.orchestration_id == orchestration_id)
        .filter(OrchestrationContext.key == key)
        .filter(
            (OrchestrationContext.agent_id == agent_id)
            if agent_id is not None
            else OrchestrationContext.agent_id.is_(None)
        )
        .first()
    )
    if existing:
        existing.value = json.dumps(value, default=str)
        existing.kind = kind
        db.commit()
        db.refresh(existing)
        return existing
    entry = OrchestrationContext(
        orchestration_id=orchestration_id,
        key=key,
        value=json.dumps(value, default=str),
        kind=kind,
        agent_id=agent_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_agent_private_context(db: Session, orchestration_id: UUID, agent_id: UUID) -> dict:
    """Return all private context entries for an agent in an orchestration."""
    rows = (
        db.query(OrchestrationContext)
        .filter(OrchestrationContext.orchestration_id == orchestration_id)
        .filter(OrchestrationContext.agent_id == agent_id)
        .all()
    )
    return {r.key: _loads(r.value) for r in rows}
