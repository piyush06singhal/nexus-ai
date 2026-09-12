"""Computer input controller — simulated input actions (Phase 10, §51).

Pure functions that validate input against the screen's element map, update
cursor/window state, and return deterministic results. Mimics what a real
input executor would do without touching a real keyboard/mouse/screen. Every
input is validated against the current screen so the simulation cannot act on
elements that are not present.
"""

from __future__ import annotations

from typing import Any

from app.external.types import ExternalValidationFailure

_BOUNDS = {"width": 1280, "height": 800}


def _resolve_element(screen: dict[str, Any], element_ref: str | None) -> dict[str, Any]:
    """Find an interactive element by id or label across all windows."""
    if not element_ref:
        raise ExternalValidationFailure("Input action requires an element reference")
    for window in screen.get("windows", []):
        for element in window.get("elements", []):
            if str(element.get("id", "")) == str(element_ref).lstrip("#"):
                return element
            if str(element.get("label", "")) == str(element_ref):
                return element
    raise ExternalValidationFailure(f"No screen element matches {element_ref!r}")


def move_mouse(screen: dict[str, Any], cursor: dict[str, Any], x: int, y: int) -> dict[str, Any]:
    x, y = max(0, min(x, _BOUNDS["width"])), max(0, min(y, _BOUNDS["height"]))
    cursor.update({"x": x, "y": y})
    return {"cursor": dict(cursor)}


def click(
    screen: dict[str, Any], cursor: dict[str, Any], element_ref: str | None
) -> dict[str, Any]:
    element = _resolve_element(screen, element_ref)
    window = next(w for w in screen["windows"] if any(e is element for e in w["elements"]))
    result: dict[str, Any] = {
        "element": element.get("id"),
        "label": element.get("label"),
        "type": element.get("type"),
        "window": window.get("title"),
    }
    if element.get("triggers"):
        result["triggers"] = element["triggers"]
    if element.get("kills_screen"):
        result["screen_dimmed"] = True
    if element.get("navigates"):
        result["navigates"] = element["navigates"]
    return result


def double_click(
    screen: dict[str, Any], cursor: dict[str, Any], element_ref: str | None
) -> dict[str, Any]:
    return {**click(screen, cursor, element_ref), "double": True}


def type_text(
    screen: dict[str, Any], cursor: dict[str, Any], element_ref: str | None, text: str
) -> dict[str, Any]:
    element = _resolve_element(screen, element_ref)
    if element.get("type") not in {"input", "textarea", "search"}:
        raise ExternalValidationFailure(f"Element {element.get('id')!r} is not typeable")
    if element.get("sensitive") and len(text) > 0:
        return {"element": element.get("id"), "typed": "••••", "sensitive": True}
    return {"element": element.get("id"), "typed": text[:64]}


def key_press(screen: dict[str, Any], cursor: dict[str, Any], key: str) -> dict[str, Any]:
    allowed = {
        "enter",
        "escape",
        "tab",
        "backspace",
        "arrow_up",
        "arrow_down",
        "arrow_left",
        "arrow_right",
        "space",
        "cmd+enter",
        "ctrl+c",
        "ctrl+v",
    }
    key = str(key).lower()
    if key not in allowed:
        raise ExternalValidationFailure(f"Key {key!r} not supported by the simulator")
    result: dict[str, Any] = {"key": key}
    if key == "enter":
        # Activate the focused window's primary button, if defined.
        for window in screen.get("windows", []):
            primary = next((e for e in window.get("elements", []) if e.get("primary")), None)
            if primary:
                result["activated"] = primary.get("label")
                result["confirm"] = bool(primary.get("confirms"))
                break
    return result


def scroll(
    screen: dict[str, Any], cursor: dict[str, Any], direction: str, amount: int = 3
) -> dict[str, Any]:
    if direction not in {"up", "down"}:
        raise ExternalValidationFailure("Scroll direction must be 'up' or 'down'")
    return {"direction": direction, "clicks": amount}


def drag(
    screen: dict[str, Any], cursor: dict[str, Any], element_ref: str | None, dx: int, dy: int
) -> dict[str, Any]:
    """Drag an element to a new offset (movement only; no drop semantics)."""
    element = _resolve_element(screen, element_ref)
    return {"element": element.get("id"), "dx": dx, "dy": dy}
