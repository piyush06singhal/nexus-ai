"""Browser interaction operations (Phase 10, §50).

Click, type, select, scroll — pure functions over the current page's
structured snapshot. They validate targets against the page's interactive map
so the simulated driver cannot click/type into elements that do not exist, and
they never carry secrets (input is validated against form/interactive schema).
"""

from __future__ import annotations

from typing import Any

from app.external.types import ExternalValidationFailure

# Deterministic cursor/viewport state for scroll simulation.
_SCREEN_DIMENSIONS = {"width": 1280, "height": 800}


def resolve_target(page: dict[str, Any], target: str | None) -> dict[str, Any]:
    """Resolve a target descriptor into a concrete interactive element."""
    if not target:
        raise ExternalValidationFailure("Interaction requires a target selector")
    interactive = page.get("interactive", [])
    if isinstance(target, dict):
        target_id = str(target.get("id", ""))
        for element in interactive:
            if str(element.get("id", "")) == target_id:
                return element
        raise ExternalValidationFailure(f"No interactive element with id {target_id!r}")
    # Simple CSS-ish selector: #id or [data-sel="..."] or bare label.
    for element in interactive:
        if str(target).lstrip("#") == str(element.get("id", "")):
            return element
        if str(target) == str(element.get("data_sel", element.get("data-sel", ""))):
            return element
        if str(target) == str(element.get("label", "")):
            return element
    raise ExternalValidationFailure(f"No interactive element matching {target!r}")


def click(page: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Click an element. Report any navigation the click performed."""
    element = dict(target)
    navigation = element.pop("navigates_to", None)
    return {
        "element": {k: v for k, v in element.items() if k in {"id", "type", "label"}},
        "navigates_to": navigation,
    }


def type_text(page: dict[str, Any], target: dict[str, Any], text: str) -> dict[str, Any]:
    """Type into an input/textarea/text field."""
    element_type = str(target.get("type", ""))
    if element_type not in {"input", "textarea", "text", "search"}:
        raise ExternalValidationFailure(f"Element {target.get('id')!r} is not typeable")
    max_len = int(target.get("max_length") or 4000)
    if len(text) > max_len:
        text = text[:max_len]
    return {
        "element": target.get("id"),
        "typed": text,
        "value_after": text[:64] + ("…" if len(text) > 64 else ""),
    }


def select(page: dict[str, Any], target: dict[str, Any], option: str) -> dict[str, Any]:
    """Select an option in a select/radio element."""
    if str(target.get("type", "")) not in {"select", "radio"}:
        raise ExternalValidationFailure(f"Element {target.get('id')!r} is not selectable")
    options = target.get("options", [])
    choice = next(
        (
            o
            for o in options
            if str(o.get("value", "")) == option or str(o.get("label", "")) == option
        ),
        None,
    )
    if choice is None:
        raise ExternalValidationFailure(f"Option {option!r} not available on {target.get('id')!r}")
    return {"element": target.get("id"), "selected": choice.get("value")}


def scroll(page: dict[str, Any], direction: str, amount: int = 300) -> dict[str, Any]:
    """Simulate a scroll that reveals more of the page's content."""
    if direction not in {"down", "up"}:
        raise ExternalValidationFailure("Scroll direction must be 'up' or 'down'")
    viewport = dict(page.get("_viewport") or {"scroll_y": 0})
    viewport["scroll_y"] = max(
        0, viewport["scroll_y"] + (amount if direction == "down" else -amount)
    )
    return {"scroll_y": viewport["scroll_y"], "viewport": _SCREEN_DIMENSIONS}
