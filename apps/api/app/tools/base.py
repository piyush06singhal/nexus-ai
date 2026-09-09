"""Base class for executable tools.

All tools in NEXUS extend :class:`BaseTool`. The base class defines the
interface the executor relies on and provides shared validation helpers
so concrete tools focus on their specific logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.tools.types import ToolDefinition, ToolParameterType, ToolResult


class BaseTool(ABC):
    """Abstract base for all executable tools.

    Subclasses must implement:
        - ``definition`` (property returning a :class:`ToolDefinition`)
        - ``execute`` (the actual tool logic)

    The executor calls ``execute`` with validated arguments and expects
    a :class:`ToolResult` back.
    """

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool's declarative definition."""
        ...

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Run the tool with the given arguments.

        Args:
            **kwargs: Keyword arguments matching the tool's parameter
                definition. All required parameters are guaranteed to be
                present; optional parameters are supplied only when the
                caller provides them.

        Returns:
            A :class:`ToolResult` describing the outcome.
        """
        ...

    def validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate and coerce *arguments* against the tool's parameter schema.

        Returns the coerced arguments dict. Raises ``ValueError`` if
        required parameters are missing or types don't match.
        """
        coerced: dict[str, Any] = {}

        for param in self.definition.parameters:
            if param.name in arguments:
                coerced[param.name] = _coerce(arguments[param.name], param.type)
            elif param.required:
                raise ValueError(f"Missing required parameter: {param.name}")
            elif param.default is not None:
                coerced[param.name] = param.default

        return coerced


def _coerce(value: Any, expected_type: ToolParameterType) -> Any:
    """Best-effort coercion of *value* to *expected_type*."""
    try:
        if expected_type == ToolParameterType.STRING:
            return str(value)
        if expected_type == ToolParameterType.INTEGER:
            return int(value)
        if expected_type == ToolParameterType.FLOAT:
            return float(value)
        if expected_type == ToolParameterType.BOOLEAN:
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
        if expected_type == ToolParameterType.ARRAY:
            if isinstance(value, list):
                return value
            raise ValueError(f"Expected list, got {type(value).__name__}")
        if expected_type == ToolParameterType.OBJECT:
            if isinstance(value, dict):
                return value
            raise ValueError(f"Expected dict, got {type(value).__name__}")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Cannot coerce {value!r} to {expected_type.value}: {exc}") from exc
    return value
