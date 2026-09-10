"""Fallback tool registry (Phase 6, spec §22).

Resolves a primary tool to a configured fallback tool. Fallback tools are
executed through the same :class:`ToolExecutor` permission path so permissions
are never bypassed (§45).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FallbackToolEntry:
    """A single fallback mapping: primary tool → fallback tool."""

    primary_tool: str
    fallback_tool: str
    fallback_args_transform: dict[str, Any] | None = None
    reason: str = ""


@dataclass
class FallbackToolRegistry:
    """Registry of tool fallbacks.

    Usage::

        registry = FallbackToolRegistry()
        registry.register("web_search", "local_search", reason="Web unavailable")
        fallback = registry.resolve("web_search")
        if fallback:
            # Execute fallback.fallback_tool instead
            ...
    """

    entries: dict[str, FallbackToolEntry] = field(default_factory=dict)

    def register(
        self,
        primary_tool: str,
        fallback_tool: str,
        fallback_args_transform: dict[str, Any] | None = None,
        reason: str = "",
    ) -> None:
        """Register a fallback for a primary tool."""
        self.entries[primary_tool] = FallbackToolEntry(
            primary_tool=primary_tool,
            fallback_tool=fallback_tool,
            fallback_args_transform=fallback_args_transform,
            reason=reason,
        )

    def resolve(self, tool_name: str) -> FallbackToolEntry | None:
        """Resolve a tool name to its fallback, if any."""
        return self.entries.get(tool_name)

    def has_fallback(self, tool_name: str) -> bool:
        """Check if a tool has a registered fallback."""
        return tool_name in self.entries

    def list_fallbacks(self) -> dict[str, str]:
        """Return a mapping of primary → fallback tool names."""
        return {e.primary_tool: e.fallback_tool for e in self.entries.values()}


# Default fallback registry for common tools
DEFAULT_FALLBACKS = FallbackToolRegistry(
    entries={
        "web_search": FallbackToolEntry(
            primary_tool="web_search",
            fallback_tool="local_search",
            reason="Web search unavailable",
        ),
        "api_call": FallbackToolEntry(
            primary_tool="api_call",
            fallback_tool="cached_response",
            reason="API unavailable",
        ),
        "code_execution": FallbackToolEntry(
            primary_tool="code_execution",
            fallback_tool="manual_review",
            reason="Execution environment unavailable",
        ),
    }
)
