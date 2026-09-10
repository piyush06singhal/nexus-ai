"""Conflict detection foundation (spec §13).

The :class:`ConflictDetector` protocol detects when two agents report
conflicting values for the same field. :class:`NumericConflictDetector` is the
deterministic default: it scans each agent's :class:`OrchestrationResult`
``structured_data`` for shared scalar keys and flags them when their values
diverge beyond a configured threshold. The interface is stable so a semantic
resolver can be added later without changing callers.
"""

from __future__ import annotations

import json
from math import isfinite
from typing import Protocol

from app.core.config import settings
from app.db.models.orchestration import OrchestrationResult
from app.orchestration.types import Conflict, ConflictDetectionError


def _loads(raw: str | None):
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


class ConflictDetector(Protocol):
    """Detect conflicting values across an orchestration's results."""

    def detect(self, results: list[OrchestrationResult]) -> list[Conflict]: ...


def _numeric_divergence(a: float, b: float) -> float:
    """Relative divergence between two numbers, 0 when both are zero."""
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom


def _scalar_conflicts(
    common_keys: set[str],
    values_by_key: dict,
    threshold: float,
) -> list[Conflict]:
    """Emit conflicts for shared numeric/boolean keys that diverge."""
    conflicts: list[Conflict] = []
    for key in sorted(common_keys):
        entries = values_by_key[key]  # list of (agent_id, value)
        # Compare every pair once; at most the field-level conflicts are few.
        for i, (agent_a, value_a) in enumerate(entries):
            for agent_b, value_b in entries[i + 1 :]:
                if value_a == value_b:
                    continue
                if isinstance(value_a, bool) or isinstance(value_b, bool):
                    kind = "boolean"
                elif isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
                    kind = "numeric"
                    if not (isfinite(value_a) and isfinite(value_b)):
                        continue
                    if _numeric_divergence(float(value_a), float(value_b)) <= threshold:
                        continue
                else:
                    kind = "status"
                    if value_a is not None and value_b is not None:
                        kind = "unknown"
                conflicts.append(
                    Conflict(
                        field=key,
                        agent_a=agent_a,
                        value_a=value_a,
                        agent_b=agent_b,
                        value_b=value_b,
                        kind=kind,
                    )
                )
    return conflicts


class NumericConflictDetector:
    """Deterministic, threshold-based conflict detection across results."""

    def __init__(self, *, threshold: float | None = None) -> None:
        # Relative divergence beyond this counts as a conflict.
        self._threshold = (
            threshold
            if threshold is not None
            else (settings.orchestration_conflict_numeric_threshold or 0.2)
        )

    def detect(self, results: list[OrchestrationResult]) -> list[Conflict]:
        """Return conflicts across *results*, or raise
        :class:`ConflictDetectionError` when a result is malformed."""
        try:
            values_by_key: dict[str, list] = {}
            for result in results:
                data = _loads(result.structured_data)
                for key, value in data.items():
                    if value is None:
                        continue
                    if not isinstance(value, (int, float, bool, str)):
                        continue
                    values_by_key.setdefault(key, []).append((result.agent_id, value))

            common_keys = {k for k, v in values_by_key.items() if len(v) > 1}
            conflicts = _scalar_conflicts(common_keys, values_by_key, self._threshold)
            # Keep the result deterministic: sort by field then agents.
            return sorted(
                conflicts,
                key=lambda c: (c.field, str(c.agent_a), str(c.agent_b)),
            )
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise ConflictDetectionError(f"Conflict detection failed: {exc}") from exc
