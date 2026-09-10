"""Workflow validation.

Validates a workflow's step graph before activation.  Checks for:
  - Unique step names within a workflow.
  - Dependencies that reference existing steps (no dangling refs).
  - No circular dependencies (cycle detection via DFS).
  - Step-type-specific configuration:
    - ``agent_task`` must have ``agent_id`` in configuration.
    - ``tool_action`` must have ``tool_name`` in configuration.
  - ``timeout_seconds`` > 0 when provided.
  - ``retry_policy`` structure is valid (if provided).

Returns a :class:`WorkflowValidationResult` with errors and warnings.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.db.models.workflow import IdempotencyTag, WorkflowStepType
from app.schemas.workflow import WorkflowValidationResult
from app.tools.registry import list_tool_names

logger = get_logger(__name__)


def _load_json(raw: str | None, field: str) -> Any:
    """Parse a JSON text field, returning ``None`` if missing/invalid."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("invalid_json_field", extra={"field": field})
        return None


def _has_cycle(edges: dict[str, set[str]]) -> bool:
    """Detect whether the directed dependency graph has a cycle.

    Uses DFS-based cycle detection on the adjacency list *edges* (name -> set
    of names it depends on).
    """
    visited: set[str] = set()
    in_stack: set[str] = set()

    def dfs(node: str) -> bool:
        if node in in_stack:
            return True  # Back-edge → cycle.
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for dep in edges.get(node, set()):
            if dep not in edges:
                continue  # Dangling ref handled elsewhere.
            if dfs(dep):
                return True
        in_stack.discard(node)
        return False

    return any(dfs(name) for name in edges)


def validate_workflow_steps(
    steps: list,
    known_agent_ids: set[str] | None = None,
    known_tool_names: list[str] | None = None,
) -> WorkflowValidationResult:
    """Validate a workflow's step definitions.

    Args:
        steps: List of ``WorkflowStep`` ORM instances (or any object with
            ``name``, ``step_type``, ``dependencies``, ``configuration``,
            ``timeout_seconds``, ``retry_policy``, ``idempotency`` attrs).
        known_agent_ids: Set of valid agent UUID strings (for ``agent_task``
            validation).  ``None`` to skip agent-reference validation.
        known_tool_names: List of registered tool names (for ``tool_action``
            validation).  ``None`` to use the live registry.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if known_tool_names is None:
        known_tool_names = list_tool_names()

    # Check: empty step list.
    if not steps:
        warnings.append("Workflow has no steps")
        return WorkflowValidationResult(valid=True, errors=errors, warnings=warnings)

    # Check: unique step names.
    names: set[str] = set()
    for step in steps:
        if step.name in names:
            errors.append(f"Duplicate step name: {step.name!r}")
        names.add(step.name)

    # Build adjacency list and validate dependencies.
    edges: dict[str, set[str]] = {}
    for step in steps:
        deps = _load_json(step.dependencies, f"{step.name}.dependencies")
        if deps is None:
            deps = []
        if not isinstance(deps, list):
            errors.append(f"Step {step.name!r}: dependencies must be a list")
            deps = []
        dep_set = set()
        for dep in deps:
            if dep not in names:
                errors.append(f"Step {step.name!r}: unknown dependency {dep!r}")
            else:
                dep_set.add(dep)
        edges[step.name] = dep_set

    # Check: no cycles.
    if _has_cycle(edges):
        errors.append("Circular dependency detected in step graph")

    # Type-specific validation.
    for step in steps:
        config = _load_json(step.configuration, f"{step.name}.configuration") or {}
        step_type = step.step_type
        if hasattr(step_type, "value"):
            step_type = step_type.value

        if step_type == WorkflowStepType.AGENT_TASK:
            agent_id = config.get("agent_id")
            if not agent_id:
                errors.append(
                    f"Step {step.name!r} (agent_task): agent_id is required in configuration"
                )
            elif known_agent_ids is not None and agent_id not in known_agent_ids:
                errors.append(f"Step {step.name!r} (agent_task): unknown agent_id {agent_id!r}")

        elif step_type == WorkflowStepType.TOOL_ACTION:
            tool_name = config.get("tool_name")
            if not tool_name:
                errors.append(
                    f"Step {step.name!r} (tool_action): tool_name is required in configuration"
                )
            elif tool_name not in known_tool_names:
                errors.append(f"Step {step.name!r} (tool_action): unknown tool {tool_name!r}")

        elif step_type == WorkflowStepType.ORCHESTRATION:
            orchestration_id = config.get("orchestration_id")
            if not orchestration_id:
                errors.append(
                    f"Step {step.name!r} (orchestration): orchestration_id is "
                    "required in configuration"
                )

        elif step_type == WorkflowStepType.CONDITION:
            condition = config.get("condition")
            if not condition or not isinstance(condition, dict):
                errors.append(
                    f"Step {step.name!r} (condition): condition dict is required in configuration"
                )

        elif step_type == WorkflowStepType.DELAY:
            duration = config.get("duration")
            if duration is None:
                errors.append(f"Step {step.name!r} (delay): duration is required in configuration")

        # Timeout validation.
        if step.timeout_seconds is not None and step.timeout_seconds <= 0:
            errors.append(f"Step {step.name!r}: timeout_seconds must be > 0")

        # Retry policy validation.
        retry = _load_json(step.retry_policy, f"{step.name}.retry_policy")
        if retry is not None:
            if not isinstance(retry, dict):
                errors.append(f"Step {step.name!r}: retry_policy must be a dict")
            else:
                max_attempts = retry.get("max_attempts", 1)
                if not isinstance(max_attempts, int) or max_attempts < 1:
                    errors.append(f"Step {step.name!r}: retry_policy.max_attempts must be >= 1")
                idempotency = step.idempotency
                if hasattr(idempotency, "value"):
                    idempotency = idempotency.value
                if max_attempts > 1 and idempotency in (
                    IdempotencyTag.SIDE_EFFECTING.value,
                    IdempotencyTag.NON_IDEMPOTENT.value,
                ):
                    warnings.append(
                        f"Step {step.name!r}: retry with max_attempts={max_attempts} "
                        f"on {idempotency} step is unsafe; retries will be skipped"
                    )

        # Verification policy validation (Phase 6, §26).
        vp = _load_json(
            getattr(step, "verification_policy", None), f"{step.name}.verification_policy"
        )
        if vp is not None:
            if not isinstance(vp, dict):
                errors.append(f"Step {step.name!r}: verification_policy must be a dict")
            else:
                strategies = vp.get("strategies")
                if strategies is not None and not isinstance(strategies, list):
                    errors.append(
                        f"Step {step.name!r}: verification_policy.strategies must be a list"
                    )
                min_score = vp.get("minimum_score")
                if min_score is not None and not (
                    isinstance(min_score, (int, float)) and 0 <= min_score <= 1
                ):
                    errors.append(
                        f"Step {step.name!r}: verification_policy.minimum_score must be 0..1"
                    )
                if vp.get("criteria") is not None and not isinstance(vp.get("criteria"), list):
                    errors.append(
                        f"Step {step.name!r}: verification_policy.criteria must be a list"
                    )

    return WorkflowValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
