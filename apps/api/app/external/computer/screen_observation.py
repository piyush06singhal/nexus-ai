"""Computer screen observation — structured, safe (Phase 10, §51).

Screen snapshots are structured (windows, UI elements, cursor) and capped at
``max_page_size_bytes``. They never include sensitive desktop content — no
clipboard contents, no passwords, no real screenshots (``screenshot_ref`` is a
placeholder in Phase 10; real screen capture is Phase 11).
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.db.models.external import ContentType
from app.external.types import ExternalObservation


def build_screen_observation(
    screen: dict[str, Any],
    cursor: dict[str, Any],
    *,
    screenshot_ref: str | None = None,
) -> ExternalObservation:
    """Build a structured, size-limited observation of the simulated screen."""
    snapshot = {
        "screen": _cap_screen(screen),
        "cursor": cursor,
    }
    return ExternalObservation(
        content_type=ContentType.EXTERNAL_UNTRUSTED_CONTENT,
        snapshot=snapshot,
        screenshot_ref=screenshot_ref,
        page_state={"simulated": True, "sensitive_windows": _sensitive_windows(screen)},
    )


def screen_json_under_cap(snapshot: dict[str, Any]) -> str:
    """Serialize a screen snapshot, guaranteeing the size cap."""
    text = json.dumps(snapshot, default=str)
    if len(text) <= settings.max_page_size_bytes:
        return text
    return text[: settings.max_page_size_bytes]


def _cap_screen(screen: dict[str, Any]) -> dict[str, Any]:
    """Limit windows/elements/text so the snapshot stays bounded."""
    windows = screen.get("windows", [])[:6]
    capped = []
    for window in windows:
        entry: dict[str, Any] = {
            "id": window.get("id"),
            "title": str(window.get("title", ""))[:128],
        }
        elements = window.get("elements", [])[:20]
        entry["elements"] = [
            {
                "id": e.get("id"),
                "type": e.get("type"),
                "label": str(e.get("label", ""))[:128],
                "value": str(e.get("value", ""))[:64] if e.get("sensitive") is not True else "••••",
            }
            for e in elements
        ]
        entry["sensitive"] = bool(window.get("sensitive"))
        capped.append(entry)
    return {"windows": capped}


def _sensitive_windows(screen: dict[str, Any]) -> list[str]:
    return [str(w.get("title", "")) for w in screen.get("windows", []) if w.get("sensitive")]
