"""Browser-use simulation: driver, session, policy, observation (Phase 10 §50).

Deterministic simulated browser; no real browser or network. Start here:
:class:`BrowserSessionManager` in :mod:`.session`.
"""

from __future__ import annotations

from app.external.browser.driver import BrowserDriver
from app.external.browser.mock_driver import MockBrowserDriver
from app.external.browser.session import BrowserSessionManager

__all__ = ["BrowserDriver", "BrowserSessionManager", "MockBrowserDriver"]
