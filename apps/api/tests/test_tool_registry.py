"""Tests for the tool registry."""

import pytest

from app.core.errors import NotFoundError, ValidationError
from app.tools.base import BaseTool
from app.tools.registry import (
    get_tool,
    get_tool_definitions,
    list_tool_names,
    register_tool,
    tool_exists,
    unregister_tool,
)
from app.tools.types import ToolDefinition, ToolParameter, ToolResult, ToolResultStatus


class DummyTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="dummy_test_tool",
            description="A dummy tool for testing",
            parameters=[
                ToolParameter(name="msg", type="string", required=True),
            ],
        )

    def execute(self, *, msg: str, **kwargs) -> ToolResult:
        return ToolResult(status=ToolResultStatus.SUCCESS, data={"echo": msg})


class TestRegistryBuiltins:
    """Tests for the built-in tools auto-registered at import time."""

    def test_all_builtin_tools_registered(self):
        names = list_tool_names()
        assert "calculator" in names
        assert "datetime" in names
        assert "text_utils" in names
        assert "json_utils" in names

    def test_get_tool_returns_base_tool(self):
        tool = get_tool("calculator")
        assert tool.definition.name == "calculator"

    def test_get_tool_unknown_raises(self):
        with pytest.raises(NotFoundError, match="not registered"):
            get_tool("nonexistent_tool")

    def test_tool_exists(self):
        assert tool_exists("calculator") is True
        assert tool_exists("nonexistent_tool") is False

    def test_get_tool_definitions_returns_list_of_dicts(self):
        defs = get_tool_definitions()
        assert isinstance(defs, list)
        assert len(defs) >= 4
        names = [d["name"] for d in defs]
        assert "calculator" in names


class TestRegistryCustom:
    """Tests for registering/unregistering custom tools."""

    def test_register_and_get(self):
        tool = DummyTool()
        register_tool(tool)
        try:
            fetched = get_tool("dummy_test_tool")
            assert fetched is tool
        finally:
            unregister_tool("dummy_test_tool")

    def test_register_duplicate_raises(self):
        tool = DummyTool()
        register_tool(tool)
        try:
            with pytest.raises(ValidationError, match="already registered"):
                register_tool(DummyTool())
        finally:
            unregister_tool("dummy_test_tool")

    def test_unregister(self):
        tool = DummyTool()
        register_tool(tool)
        unregister_tool("dummy_test_tool")
        assert not tool_exists("dummy_test_tool")

    def test_unregister_nonexistent_noop(self):
        unregister_tool("this_does_not_exist")  # should not raise
