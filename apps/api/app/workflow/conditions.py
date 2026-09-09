"""Workflow condition evaluation.

Implements a small, safe condition evaluator for workflow branching.  No
``eval()``, no arbitrary code execution — conditions are evaluated via a
controlled set of comparison operators over values resolved from the
structured workflow state.

Supported condition formats::

    {"field": "steps.A.output.lead_count", "op": ">", "value": 50}

    {"and": [ ... ]}

    {"or":  [ ... ]}

Nested ``and``/``or`` conditions are supported recursively.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_contains"}


class ConditionEvaluationError(Exception):
    """Raised when a condition cannot be evaluated."""


def resolve_path(state: dict, path: str) -> Any:
    """Resolve a dotted path like ``steps.A.output.lead_count`` from *state*.

    Returns the resolved value, or raises ``ConditionEvaluationError`` if the
    path does not exist (so callers can distinguish "missing" from ``None``).
    """
    if not path:
        raise ConditionEvaluationError("Empty path")

    parts = path.split(".")
    current: Any = state
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ConditionEvaluationError(f"Path {path!r} not found (failed at {part!r})")
    return current


def _compare(actual: Any, op: str, expected: Any) -> bool:
    """Evaluate a single comparison."""
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "gt":
        return actual > expected
    if op == "gte":
        return actual >= expected
    if op == "lt":
        return actual < expected
    if op == "lte":
        return actual <= expected
    if op == "contains":
        if not isinstance(actual, str) and not isinstance(actual, (list, tuple)):
            return False
        return expected in actual
    if op == "not_contains":
        if not isinstance(actual, str) and not isinstance(actual, (list, tuple)):
            return True
        return expected not in actual
    raise ConditionEvaluationError(f"Unknown operator: {op!r}")


def evaluate_condition(condition: dict, state: dict) -> bool:
    """Evaluate a condition against the workflow state.

    Returns ``True`` if the condition passes, ``False`` otherwise.

    Raises ``ConditionEvaluationError`` if the condition is malformed or a
    referenced path does not exist in the state.
    """
    if not condition:
        return True  # Empty condition always passes.

    # Handle logical operators.
    if "and" in condition:
        sub_conditions: list[dict] = condition["and"]
        return all(evaluate_condition(sc, state) for sc in sub_conditions)

    if "or" in condition:
        sub_conditions = condition["or"]
        return any(evaluate_condition(sc, state) for sc in sub_conditions)

    # Handle a single comparison: {field, op, value}.
    if "field" in condition and "op" in condition and "value" in condition:
        field = condition["field"]
        op = condition["op"]

        if op not in OPS:
            raise ConditionEvaluationError(f"Invalid operator: {op!r}")

        actual = resolve_path(state, field)
        expected = condition["value"]
        return _compare(actual, op, expected)

    raise ConditionEvaluationError(
        f"Invalid condition format: expected 'and'/'or' or 'field'/'op'/'value', "
        f"got keys {sorted(condition.keys())}"
    )
