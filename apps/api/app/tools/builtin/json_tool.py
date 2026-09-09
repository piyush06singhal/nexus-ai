"""JSON utility tool — parse, validate, query, and format JSON data.

All operations are pure transformations with no side effects.
"""

from __future__ import annotations

import json
from typing import Any

from app.tools.base import BaseTool
from app.tools.types import (
    ToolDefinition,
    ToolParameter,
    ToolParameterType,
    ToolResult,
    ToolResultStatus,
)


class JsonUtilityTool(BaseTool):
    """Parse, validate, pretty-print, and query JSON data."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="json_utils",
            description="Parse, validate, pretty-print, minify, or query JSON data.",
            parameters=[
                ToolParameter(
                    name="action",
                    type=ToolParameterType.STRING,
                    description="Action: 'parse', 'validate', 'pretty', 'minify', 'query', 'keys'",
                    required=True,
                    enum=["parse", "validate", "pretty", "minify", "query", "keys"],
                ),
                ToolParameter(
                    name="data",
                    type=ToolParameterType.STRING,
                    description="JSON string to operate on.",
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    type=ToolParameterType.STRING,
                    description="Dot-separated key path for 'query' action (e.g. 'user.name').",
                    required=False,
                ),
            ],
            dangerous=False,
            timeout_seconds=5.0,
            tags=["data", "utility", "json"],
        )

    def execute(self, *, action: str, data: str, **kwargs: Any) -> ToolResult:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            if action in ("validate",):
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    data={"valid": False, "error": str(exc)},
                )
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Invalid JSON: {exc}",
            )

        try:
            if action == "parse":
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    data={"parsed": parsed, "type": type(parsed).__name__},
                )
            if action == "validate":
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    data={"valid": True, "type": type(parsed).__name__},
                )
            if action == "pretty":
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    data={"formatted": json.dumps(parsed, indent=2, default=str)},
                )
            if action == "minify":
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    data={"minified": json.dumps(parsed, separators=(",", ":"), default=str)},
                )
            if action == "query":
                path = kwargs.get("path", "")
                value = self._query_path(parsed, path)
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    data={"path": path, "value": value},
                )
            if action == "keys":
                if isinstance(parsed, dict):
                    return ToolResult(
                        status=ToolResultStatus.SUCCESS,
                        data={"keys": list(parsed.keys())},
                    )
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"Top-level JSON is {type(parsed).__name__}, not an object",
                )
            return ToolResult(status=ToolResultStatus.ERROR, error=f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"JSON operation failed: {exc}")

    @staticmethod
    def _query_path(data: Any, path: str) -> Any:
        """Traverse a dot-separated path through nested dicts/lists."""
        if not path:
            return data
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise KeyError(f"Path '{path}' not found in JSON data")
        return current
