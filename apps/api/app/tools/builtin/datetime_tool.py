"""Date/time tool — returns current time, formats dates, and computes deltas.

All operations are read-only with no side effects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.tools.base import BaseTool
from app.tools.types import (
    ToolDefinition,
    ToolParameter,
    ToolParameterType,
    ToolResult,
    ToolResultStatus,
)


class DateTimeTool(BaseTool):
    """Provides date/time information and basic formatting."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="datetime",
            description="Get current date/time, format timestamps, or compute time differences.",
            parameters=[
                ToolParameter(
                    name="action",
                    type=ToolParameterType.STRING,
                    description=(
                        "Action: 'now' (current time), "
                        "'format' (format a timestamp), "
                        "'diff' (days between two dates)"
                    ),
                    required=True,
                    enum=["now", "format", "diff"],
                ),
                ToolParameter(
                    name="timestamp",
                    type=ToolParameterType.STRING,
                    description="ISO 8601 timestamp string (for format/diff actions).",
                    required=False,
                ),
                ToolParameter(
                    name="timestamp2",
                    type=ToolParameterType.STRING,
                    description="Second ISO 8601 timestamp (for diff action).",
                    required=False,
                ),
                ToolParameter(
                    name="fmt",
                    type=ToolParameterType.STRING,
                    description=(
                        "strftime format string (for format action). Default: '%Y-%m-%d %H:%M:%S'."
                    ),
                    required=False,
                    default="%Y-%m-%d %H:%M:%S",
                ),
            ],
            dangerous=False,
            timeout_seconds=5.0,
            tags=["datetime", "utility"],
        )

    def execute(self, *, action: str, **kwargs: Any) -> ToolResult:
        try:
            if action == "now":
                return self._action_now()
            if action == "format":
                return self._action_format(**kwargs)
            if action == "diff":
                return self._action_diff(**kwargs)
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Unknown action: {action}",
            )
        except Exception as exc:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Datetime operation failed: {exc}",
            )

    def _action_now(self) -> ToolResult:
        now = datetime.now(UTC)
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            data={
                "datetime": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "unix_timestamp": now.timestamp(),
            },
        )

    def _action_format(
        self,
        *,
        timestamp: str | None = None,
        fmt: str = "%Y-%m-%d %H:%M:%S",
        **_: Any,
    ) -> ToolResult:
        if timestamp is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="timestamp parameter is required for format action",
            )
        dt = datetime.fromisoformat(timestamp)
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            data={"formatted": dt.strftime(fmt), "original": timestamp, "format": fmt},
        )

    def _action_diff(
        self,
        *,
        timestamp: str | None = None,
        timestamp2: str | None = None,
        **_: Any,
    ) -> ToolResult:
        if timestamp is None or timestamp2 is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="Both timestamp and timestamp2 are required for diff action",
            )
        dt1 = datetime.fromisoformat(timestamp)
        dt2 = datetime.fromisoformat(timestamp2)
        delta = dt2 - dt1
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            data={
                "days": delta.days,
                "total_seconds": int(delta.total_seconds()),
                "from": timestamp,
                "to": timestamp2,
            },
        )
