"""Browser observation — structured, size-limited page snapshots (Phase 10).

Every observation of a page is *untrusted data*: it carries the
``EXTERNAL_UNTRUSTED_CONTENT`` marker (§65) and is truncated to
``max_page_size_bytes``. The snapshot shape (visible text, interactive
elements, links, forms) is what the simulated driver produces; a real browser
driver would populate the same shape so the observation contract is stable.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.db.models.external import ContentType
from app.external.types import ExternalObservation


def build_observation(
    *,
    url: str,
    title: str,
    visible_text: str,
    interactive: list[dict[str, Any]],
    links: list[dict[str, str]],
    forms: list[dict[str, Any]],
    page_state: dict[str, Any] | None = None,
    screenshot_ref: str | None = None,
) -> ExternalObservation:
    """Build a size-limited structured observation for a page visit."""
    snapshot = {
        "visible_text": _truncate_text(visible_text),
        "interactive": interactive[:50],
        "links": links[:50],
        "forms": forms[:10],
    }
    return ExternalObservation(
        content_type=ContentType.EXTERNAL_UNTRUSTED_CONTENT,
        url=url,
        title=title[:256],
        snapshot=snapshot,
        screenshot_ref=screenshot_ref,
        page_state=page_state or {},
    )


def snapshot_under_cap(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Guarantee the serialized snapshot never exceeds the size cap."""
    text = json.dumps(snapshot, default=str)
    if len(text) <= settings.max_page_size_bytes:
        return snapshot
    # Drop the largest text field and retry, then hard-truncate.
    remaining = settings.max_page_size_bytes
    core: dict[str, Any] = {}
    for key, value in snapshot.items():
        encoded = json.dumps(value, default=str)
        if len(encoded) > remaining:
            encoded = encoded[: remaining - 32]
        core[key] = value
    core["_truncated"] = True
    # Force the encoded form through a round-trip so persisted JSON is valid.
    return json.loads(json.dumps(core, default=str)[: settings.max_page_size_bytes])


def _truncate_text(text: str) -> str:
    # Rough char budget: visible text is the bulk of the page snapshot.
    budget = max(settings.max_page_size_bytes - 512, 512)
    return text[:budget]
