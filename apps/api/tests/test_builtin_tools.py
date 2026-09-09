"""Tests for built-in tools: calculator, datetime, text_utils, json_utils."""

import pytest

from app.tools.builtin.calculator import CalculatorTool
from app.tools.builtin.datetime_tool import DateTimeTool
from app.tools.builtin.json_tool import JsonUtilityTool
from app.tools.builtin.text_tool import TextUtilityTool
from app.tools.types import ToolResultStatus

# ---------------------------------------------------------------------------
# Calculator tool
# ---------------------------------------------------------------------------


class TestCalculatorTool:
    def setup_method(self):
        self.tool = CalculatorTool()

    def test_definition_has_required_fields(self):
        d = self.tool.definition
        assert d.name == "calculator"
        assert len(d.parameters) == 1
        assert d.parameters[0].name == "expression"

    def test_addition(self):
        result = self.tool.execute(expression="2 + 3")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == 5.0

    def test_subtraction(self):
        result = self.tool.execute(expression="10 - 4")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == 6.0

    def test_multiplication(self):
        result = self.tool.execute(expression="3 * 7")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == 21.0

    def test_division(self):
        result = self.tool.execute(expression="15 / 3")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == 5.0

    def test_division_by_zero(self):
        result = self.tool.execute(expression="10 / 0")
        assert result.status == ToolResultStatus.ERROR
        assert "Division by zero" in result.error

    def test_floor_division(self):
        result = self.tool.execute(expression="7 // 2")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == 3.0

    def test_modulo(self):
        result = self.tool.execute(expression="10 % 3")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == 1.0

    def test_power(self):
        result = self.tool.execute(expression="2 ** 10")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == 1024.0

    def test_sqrt(self):
        result = self.tool.execute(expression="sqrt(16)")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == 4.0

    def test_single_number(self):
        result = self.tool.execute(expression="42")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == 42.0

    def test_invalid_expression(self):
        result = self.tool.execute(expression="hello world")
        assert result.status == ToolResultStatus.ERROR

    def test_validate_arguments_missing(self):
        with pytest.raises(ValueError, match="Missing required"):
            self.tool.validate_arguments({})

    def test_validate_arguments_coerces_string(self):
        result = self.tool.validate_arguments({"expression": "1 + 1"})
        assert result["expression"] == "1 + 1"


# ---------------------------------------------------------------------------
# DateTime tool
# ---------------------------------------------------------------------------


class TestDateTimeTool:
    def setup_method(self):
        self.tool = DateTimeTool()

    def test_now(self):
        result = self.tool.execute(action="now")
        assert result.status == ToolResultStatus.SUCCESS
        assert "datetime" in result.data
        assert "date" in result.data
        assert "time" in result.data
        assert "unix_timestamp" in result.data

    def test_format(self):
        result = self.tool.execute(
            action="format",
            timestamp="2025-06-15T12:30:00",
            fmt="%Y/%m/%d",
        )
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["formatted"] == "2025/06/15"

    def test_format_missing_timestamp(self):
        result = self.tool.execute(action="format")
        assert result.status == ToolResultStatus.ERROR
        assert "timestamp" in result.error.lower()

    def test_diff(self):
        result = self.tool.execute(
            action="diff",
            timestamp="2025-01-01T00:00:00",
            timestamp2="2025-01-11T00:00:00",
        )
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["days"] == 10

    def test_diff_missing_params(self):
        result = self.tool.execute(action="diff")
        assert result.status == ToolResultStatus.ERROR

    def test_unknown_action(self):
        result = self.tool.execute(action="unknown")
        assert result.status == ToolResultStatus.ERROR


# ---------------------------------------------------------------------------
# Text utility tool
# ---------------------------------------------------------------------------


class TestTextUtilityTool:
    def setup_method(self):
        self.tool = TextUtilityTool()

    def test_upper_case(self):
        result = self.tool.execute(action="case", text="hello", case_type="upper")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == "HELLO"

    def test_lower_case(self):
        result = self.tool.execute(action="case", text="HELLO", case_type="lower")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == "hello"

    def test_title_case(self):
        result = self.tool.execute(action="case", text="hello world", case_type="title")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == "Hello World"

    def test_word_count(self):
        result = self.tool.execute(action="words", text="hello world foo")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["word_count"] == 3
        assert result.data["char_count"] == 15

    def test_trim(self):
        result = self.tool.execute(action="trim", text="  hello  ")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["trimmed"] == "hello"

    def test_replace(self):
        result = self.tool.execute(
            action="replace",
            text="hello world",
            substring="world",
            replacement="there",
        )
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["result"] == "hello there"

    def test_reverse(self):
        result = self.tool.execute(action="reverse", text="abc")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["reversed"] == "cba"

    def test_count_substring(self):
        result = self.tool.execute(action="count", text="banana", substring="an")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["count"] == 2

    def test_unknown_action(self):
        result = self.tool.execute(action="unknown", text="x")
        assert result.status == ToolResultStatus.ERROR


# ---------------------------------------------------------------------------
# JSON utility tool
# ---------------------------------------------------------------------------


class TestJsonUtilityTool:
    def setup_method(self):
        self.tool = JsonUtilityTool()

    def test_parse(self):
        result = self.tool.execute(action="parse", data='{"a": 1}')
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["parsed"] == {"a": 1}

    def test_validate_valid(self):
        result = self.tool.execute(action="validate", data='{"x": true}')
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["valid"] is True

    def test_validate_invalid(self):
        result = self.tool.execute(action="validate", data="not json")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["valid"] is False

    def test_pretty(self):
        result = self.tool.execute(action="pretty", data='{"a":1}')
        assert result.status == ToolResultStatus.SUCCESS
        assert "\n" in result.data["formatted"]

    def test_minify(self):
        result = self.tool.execute(action="minify", data='{"a": 1, "b": 2}')
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["minified"] == '{"a":1,"b":2}'

    def test_query(self):
        data = '{"user": {"name": "Alice"}}'
        result = self.tool.execute(action="query", data=data, path="user.name")
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data["value"] == "Alice"

    def test_query_missing_path(self):
        result = self.tool.execute(action="query", data='{"a":1}', path="b")
        assert result.status == ToolResultStatus.ERROR

    def test_keys(self):
        result = self.tool.execute(action="keys", data='{"a":1,"b":2}')
        assert result.status == ToolResultStatus.SUCCESS
        assert set(result.data["keys"]) == {"a", "b"}

    def test_keys_non_object(self):
        result = self.tool.execute(action="keys", data="[1,2,3]")
        assert result.status == ToolResultStatus.ERROR

    def test_invalid_json(self):
        result = self.tool.execute(action="parse", data="not json")
        assert result.status == ToolResultStatus.ERROR
