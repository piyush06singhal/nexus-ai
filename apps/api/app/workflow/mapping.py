"""Workflow input mapping resolution.

Maps step input parameters to concrete values from the structured workflow
state.  Mapping specifications are expressed as dotted-path references:

    {"param1": "steps.A.output.x", "param2": "input.region"}

This keeps step configurations data-driven and allows arbitrary (but
safe) wiring between steps without code.
"""

from __future__ import annotations

from typing import Any

from app.workflow.conditions import resolve_path


def resolve_mapping(
    mapping: dict[str, Any] | None,
    state: dict,
) -> dict[str, Any]:
    """Resolve a mapping dict by replacing path references with real values.

    If *mapping* is ``None`` or empty, returns an empty dict.  Values that are
    plain strings referring to a known path are resolved; values that are
    non-string primitives (int, float, bool, None) are passed through
    unchanged, as are dicts/lists (enabling literal nested inputs).
    """
    if not mapping:
        return {}

    result: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, str):
            # Strings are interpreted as path references.
            try:
                result[key] = resolve_path(state, value)
            except Exception:
                # If the path doesn't exist, fall back to None — allows
                # optional references (the engine will handle missing data).
                result[key] = None
        else:
            # Non-string values (int, float, bool, dict, list, None) are literals.
            result[key] = value

    return result
