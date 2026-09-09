"""Tool system.

Provides the tool abstraction (BaseTool, ToolDefinition), a central registry
for tool resolution, an executor with permission checking and timeout
enforcement, and built-in utility tools.
"""

from app.tools.base import BaseTool
from app.tools.registry import get_tool, get_tool_definitions, list_tool_names, register_tool
from app.tools.types import ToolDefinition, ToolParameter, ToolResult

__all__ = [
    "BaseTool",
    "ToolDefinition",
    "ToolParameter",
    "ToolResult",
    "get_tool",
    "get_tool_definitions",
    "list_tool_names",
    "register_tool",
]
