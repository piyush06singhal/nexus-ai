"""Computer-use simulation: driver, session, policy, screen observation (§51).

Deterministic simulated desktop; no real desktop or screenshot. Start here:
:class:`ComputerSessionManager` in :mod:`.session`.
"""

from __future__ import annotations

from app.external.computer.driver import ComputerDriver
from app.external.computer.mock_driver import MockComputerDriver
from app.external.computer.session import ComputerSessionManager

__all__ = ["ComputerDriver", "ComputerSessionManager", "MockComputerDriver"]
