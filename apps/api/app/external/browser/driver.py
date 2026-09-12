"""Browser driver protocol (Phase 10, §50).

The seam a real browser driver (Playwright, Phase 11 hardening) would also
implement: resolve URLs to pages, produce structured observations, and report
blocked/adversarial pages. Phase 10 ships the deterministic
:class:`MockBrowserDriver`; the protocol keeps the session manager
provider-independent.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.external.types import ExternalObservation


@runtime_checkable
class BrowserDriver(Protocol):
    """Minimal simulated-browser driver surface used by the session manager."""

    def resolve(self, url: str) -> dict[str, Any]:
        """Resolve a URL to its fixture page (raises on unknown URLs)."""

    def observe(self, page: dict[str, Any]) -> ExternalObservation:
        """Produce a size-limited untrusted observation of a page."""

    def is_blocked_page(self, page: dict[str, Any]) -> bool:
        """Whether the page is a known adversarial/injection fixture."""
