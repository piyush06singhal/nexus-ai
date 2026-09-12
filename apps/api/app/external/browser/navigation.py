"""Browser navigation operations (Phase 10, §50).

Pure functions over a page-catalog driver: resolve a URL to a page, move
back/forward/refresh. Deterministic and bounded — the driver owns the catalog
and these helpers define how *state transitions* work (URL resolution, history
stack, navigation counting), leaving policy/approval to the session manager.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.external.types import ExternalValidationFailure


class BrowserPageNotFound(ValueError):
    """The requested URL has no page in the driver catalog."""


def open_page(
    url: str,
    *,
    resolve: Callable[[str], dict[str, Any]],
    history: list[dict[str, Any]],
    forward_stack: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve *url* and push the resulting page onto *history*.

    Returns the resolved page dict. ``history`` is the back stack; any pending
    forward pages are cleared on a fresh navigation (standard browser model).
    """
    page = resolve(url)
    history.append(page)
    forward_stack.clear()
    return page


def navigate_to(
    url: str,
    *,
    resolve: Callable[[str], dict[str, Any]],
    history: list[dict[str, Any]],
    forward_stack: list[dict[str, Any]],
) -> dict[str, Any]:
    """Alias of :func:`open_page` for the NAVIGATE action."""
    return open_page(url, resolve=resolve, history=history, forward_stack=forward_stack)


def go_back(history: list[dict[str, Any]], forward_stack: list[dict[str, Any]]) -> dict[str, Any]:
    """Move one entry back in history; raises when there is nothing behind."""
    if len(history) < 2:
        raise ExternalValidationFailure("No previous page to go back to")
    current = history.pop()
    forward_stack.append(current)
    return history[-1]


def go_forward(
    history: list[dict[str, Any]], forward_stack: list[dict[str, Any]]
) -> dict[str, Any]:
    """Move one entry forward; raises when there is nothing ahead."""
    if not forward_stack:
        raise ExternalValidationFailure("No forward page to go to")
    page = forward_stack.pop()
    history.append(page)
    return page


def refresh(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Re-load the current page (same URL) — no state change otherwise."""
    if not history:
        raise ExternalValidationFailure("No current page to refresh")
    return history[-1]
