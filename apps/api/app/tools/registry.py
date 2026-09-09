"""Tool registry.

A central registry mapping tool name -> tool instance. The executor and
the runtime resolve tools through this registry — no tool is callable
without being registered here first.

Built-in tools are auto-registered at import time so they're available
immediately. External/custom tools register via ``register_tool``.
"""

from __future__ import annotations

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.tools.base import BaseTool

logger = get_logger(__name__)

# name -> tool instance (singleton per tool)
_TOOL_INSTANCES: dict[str, BaseTool] = {}


def register_tool(tool: BaseTool) -> None:
    """Register a tool instance. Raises if the name is already taken."""
    name = tool.definition.name
    if name in _TOOL_INSTANCES:
        raise ValidationError(f"Tool {name!r} is already registered")
    _TOOL_INSTANCES[name] = tool
    logger.info("tool_registered", extra={"tool": name})


def unregister_tool(name: str) -> None:
    """Remove a tool from the registry. No-op if not registered."""
    _TOOL_INSTANCES.pop(name, None)


def get_tool(name: str) -> BaseTool:
    """Return a registered tool by name. Raises ``NotFoundError`` if missing."""
    if name not in _TOOL_INSTANCES:
        raise NotFoundError(f"Tool {name!r} is not registered")
    return _TOOL_INSTANCES[name]


def get_tool_definitions() -> list[dict]:
    """Return all registered tool definitions as serializable dicts."""
    return [tool.definition.model_dump() for tool in _TOOL_INSTANCES.values()]


def list_tool_names() -> list[str]:
    """Return sorted names of all registered tools."""
    return sorted(_TOOL_INSTANCES.keys())


def tool_exists(name: str) -> bool:
    """Check whether a tool is registered."""
    return name in _TOOL_INSTANCES


# ---------------------------------------------------------------------------
# Auto-register built-in tools at import time.
# ---------------------------------------------------------------------------


def _register_builtins() -> None:
    """Register all built-in tools. Called once at module load."""
    from app.tools.builtin.calculator import CalculatorTool
    from app.tools.builtin.datetime_tool import DateTimeTool
    from app.tools.builtin.json_tool import JsonUtilityTool
    from app.tools.builtin.text_tool import TextUtilityTool

    for tool_cls in (CalculatorTool, DateTimeTool, TextUtilityTool, JsonUtilityTool):
        tool = tool_cls()
        _TOOL_INSTANCES[tool.definition.name] = tool


_register_builtins()
