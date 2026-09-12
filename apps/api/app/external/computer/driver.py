"""Computer driver protocol (Phase 10, §51).

The seam a real desktop driver (Phase 11 hardening) would also implement:
snapshot/observe the screen, perform input actions, and report whether an input
is sensitive. Phase 10 ships the deterministic :class:`MockComputerDriver`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.external.types import ExternalObservation


@runtime_checkable
class ComputerDriver(Protocol):
    def snapshot(self) -> dict[str, Any]:
        """Current simulated screen state."""

    @property
    def cursor(self) -> dict[str, Any]:
        """Current cursor position."""

    def observe(self) -> ExternalObservation:
        """Structured, size-limited screen observation."""

    def perform(self, action_type: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Dispatch one input action against the simulated desk."""

    def is_sensitive(self, action_type: str, input_data: dict[str, Any]) -> bool:
        """Whether the input targets the purchase/sensitive path."""
