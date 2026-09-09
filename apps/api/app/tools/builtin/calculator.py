"""Calculator tool — evaluates mathematical expressions safely.

Supports basic arithmetic, exponentiation, and common math functions
without requiring ``eval`` or external dependencies.
"""

from __future__ import annotations

import math
import operator
from typing import Any

from app.tools.base import BaseTool
from app.tools.types import (
    ToolDefinition,
    ToolParameter,
    ToolParameterType,
    ToolResult,
    ToolResultStatus,
)

# Safe binary operators the calculator supports.
_BINARY_OPS: dict[str, Any] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
}

# Safe unary/math functions.
_UNARY_OPS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "ceil": math.ceil,
    "floor": math.floor,
}


class CalculatorTool(BaseTool):
    """Evaluates a mathematical expression and returns the numeric result."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calculator",
            description="Evaluate a mathematical expression and return the numeric result.",
            parameters=[
                ToolParameter(
                    name="expression",
                    type=ToolParameterType.STRING,
                    description="The math expression to evaluate (e.g. '2 + 3 * 4', 'sqrt(16)')",
                    required=True,
                ),
            ],
            dangerous=False,
            timeout_seconds=5.0,
            tags=["math", "utility"],
        )

    def execute(self, *, expression: str, **kwargs: Any) -> ToolResult:
        try:
            result = self._safe_eval(expression)
            return ToolResult(status=ToolResultStatus.SUCCESS, data={"result": result})
        except Exception as exc:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Failed to evaluate expression: {exc}",
            )

    def _safe_eval(self, expression: str) -> float:
        """Evaluate a math expression using a restricted parser."""
        # Normalize the expression.
        expr = expression.strip()

        # Try simple binary operations first.
        for op_str, op_fn in sorted(_BINARY_OPS.items(), key=lambda x: -len(x[0])):
            # Only split on the *last* occurrence to respect operator precedence
            # for multi-char ops like '**' and '//'.
            parts = expr.rsplit(op_str, 1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                left = self._safe_eval(parts[0])
                right = self._safe_eval(parts[1])
                if op_str in ("/", "//") and right == 0:
                    raise ZeroDivisionError("Division by zero")
                return op_fn(left, right)

        # Try function calls: func(arg)
        for func_name, func in _UNARY_OPS.items():
            if expr.startswith(f"{func_name}(") and expr.endswith(")"):
                inner = expr[len(func_name) + 1 : -1].strip()
                arg = self._safe_eval(inner)
                return func(arg)

        # Try parsing as a number.
        try:
            return float(expr)
        except ValueError as exc:
            raise ValueError(
                f"Cannot parse '{expr}' as a number or recognized expression"
            ) from exc
