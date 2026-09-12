"""Deterministic simulated computer driver (Phase 10, §51).

An in-repo driver simulating a desktop: a bounded set of windows with UI
elements, a cursor, and deterministic responses to input actions. The desk
deliberately includes a *purchase fixture* (§67): a checkout window whose
"Confirm purchase" flow is a sensitive, approval-gated path — the simulator
reports the intent, the policy layer parks it, and only an approved
``EXTERNAL_ACTION_APPROVAL`` gate lets it run. No real desktop, no screenshots,
no real payments anywhere.
"""

from __future__ import annotations

from typing import Any

from app.external.computer.input_controller import (
    click,
    double_click,
    drag,
    key_press,
    move_mouse,
    scroll,
    type_text,
)
from app.external.computer.screen_observation import build_screen_observation
from app.external.types import ExternalObservation, ExternalValidationFailure

_FOCUSED_APP = "nexus-desk"

# A desk = one focused window per app; deterministic fixture.
_DESK: dict[str, Any] = {
    "focus": _FOCUSED_APP,
    "windows": [
        {
            "id": "win-desk",
            "title": "NEXUS Desk",
            "sensitive": False,
            "focused": True,
            "elements": [
                {"id": "welcome", "type": "label", "label": "Welcome to NEXUS Desk"},
                {
                    "id": "btn-reports",
                    "type": "button",
                    "label": "Open reports",
                    "navigates": "reports",
                },
                {
                    "id": "btn-compose",
                    "type": "button",
                    "label": "Compose message",
                    "navigates": "compose",
                },
                {
                    "id": "btn-purchase",
                    "type": "button",
                    "label": "Purchase plan",
                    "navigates": "checkout",
                },
            ],
        },
        {
            "id": "win-reports",
            "title": "Reports",
            "sensitive": False,
            "elements": [
                {
                    "id": "lbl-rep1",
                    "type": "label",
                    "label": "Q3 usage: +23% connected integrations",
                },
                {"id": "btn-export", "type": "button", "label": "Export CSV"},
            ],
        },
        {
            "id": "win-compose",
            "title": "Compose",
            "sensitive": False,
            "elements": [
                {"id": "fld-to", "type": "input", "label": "To"},
                {"id": "fld-subject", "type": "input", "label": "Subject"},
                {"id": "fld-body", "type": "textarea", "label": "Body"},
                {
                    "id": "btn-send",
                    "type": "button",
                    "label": "Send",
                    "confirms": True,
                    "primary": True,
                },
            ],
        },
        {
            "id": "win-checkout",
            "title": "Checkout — purchase plan",
            "sensitive": True,
            "elements": [
                {"id": "lbl-plan", "type": "label", "label": "Enterprise plan — $299/seat/mo"},
                {"id": "fld-cc", "type": "input", "label": "Card number", "sensitive": True},
                {"id": "fld-cvv", "type": "input", "label": "CVV", "sensitive": True},
                {
                    "id": "btn-confirm",
                    "type": "button",
                    "label": "Confirm purchase",
                    "purchase": True,
                    "primary": True,
                },
            ],
        },
    ],
}


class MockComputerDriver:
    """Driver over the simulated desk; pure state transitions + observations."""

    def __init__(self) -> None:
        self._desk = _DESK
        self._cursor = {"x": 40, "y": 32}

    def snapshot(self) -> dict[str, Any]:
        """Cloned desk state (no shared references leak to callers)."""
        import copy

        return copy.deepcopy(self._desk)

    @property
    def cursor(self) -> dict[str, Any]:
        return dict(self._cursor)

    def observe(self) -> ExternalObservation:
        return build_screen_observation(
            self.snapshot(),
            self.cursor,
            screenshot_ref=f"screen-sim-{_FOCUSED_APP}",
        )

    def perform(self, action_type: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Dispatch one input action against the simulated desk."""
        screen = self.snapshot()
        element_ref = str(
            (input_data or {}).get("element") or (input_data or {}).get("selector") or ""
        )
        if action_type == "move_mouse":
            return move_mouse(
                screen, self._cursor, int(input_data.get("x", 40)), int(input_data.get("y", 32))
            )
        if action_type == "click":
            return click(screen, self._cursor, element_ref or None)
        if action_type == "double_click":
            return double_click(screen, self._cursor, element_ref or None)
        if action_type == "type":
            return type_text(
                screen, self._cursor, element_ref or None, str(input_data.get("text", ""))
            )
        if action_type == "key_press":
            return key_press(screen, self._cursor, str(input_data.get("key", "")))
        if action_type == "scroll":
            return scroll(
                screen,
                self._cursor,
                str(input_data.get("direction", "down")),
                int(input_data.get("amount", 3)),
            )
        if action_type == "drag":
            return drag(
                screen,
                self._cursor,
                element_ref or None,
                int(input_data.get("dx", 0)),
                int(input_data.get("dy", 0)),
            )
        if action_type == "screenshot":
            return {"screenshot_ref": "screen-sim-screenshot", "placeholder": True}
        if action_type == "wait":
            return {"waited": True}
        raise ExternalValidationFailure(f"Unsupported computer action {action_type!r}")

    def is_sensitive(self, action_type: str, input_data: dict[str, Any]) -> bool:
        """Whether an input targets the purchase/sensitive path (used by policy)."""
        if action_type == "click":
            element_ref = str(
                (input_data or {}).get("element") or (input_data or {}).get("selector") or ""
            )
            element = _find_element(self._desk, element_ref)
            return bool(element and (element.get("purchase") or element.get("sensitive")))
        if action_type == "key_press":
            key = str((input_data or {}).get("key", "")).lower()
            confirm = key == "enter" and _focused_window(self._desk).get("sensitive")
            return bool(confirm)
        if action_type == "type":
            element_ref = str(
                (input_data or {}).get("element") or (input_data or {}).get("selector") or ""
            )
            element = _find_element(self._desk, element_ref)
            return bool(element and element.get("sensitive"))
        return False


def _find_element(desk: dict[str, Any], element_ref: str) -> dict[str, Any] | None:
    for window in desk["windows"]:
        for element in window["elements"]:
            if (
                str(element.get("id", "")) == element_ref.lstrip("#")
                or str(element.get("label", "")) == element_ref
            ):
                return element
    return None


def _focused_window(desk: dict[str, Any]) -> dict[str, Any]:
    for window in desk["windows"]:
        if window.get("focused"):
            return window
    return desk["windows"][0]
