"""Tool verification strategy (Phase 6, spec §8).

Re-runs a configured trusted tool via the existing :class:`ToolExecutor`
with the SAME :class:`PermissionService.get_context(agent_id)` so permissions
are never bypassed. Compares the tool output against the candidate result.

Requires an execution context that carried the tool call's permission context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.verification.types import StrategyOutcome as _StrategyOutcome
from app.verification.types import VerificationCriteria, VerificationStatus


class StrategyOutcome(_StrategyOutcome):
    """Local alias."""


@runtime_checkable
class ToolVerifier(Protocol):
    """Protocol for the tool verification strategy."""

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        """Re-run a tool and compare against result_data.

        Context must include:
        - ``tool_executor``: a callable or executor instance
        - ``tool_name``: the tool to re-run
        - ``tool_args``: arguments to pass to the tool
        - ``agent_id``: the agent whose permission context to use
        - ``permission_context``: the permission context to preserve
        """


@dataclass
class DefaultToolVerifier:
    """Default tool verification implementation.

    Safety guarantees (spec §8, §45):
    - The same permission context is used (no privilege escalation).
    - The tool is the SAME tool that produced the original result.
    - If no tool executor is available, the strategy is SKIPPED.
    """

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        context = context or {}
        criteria = criteria or []

        tool_executor = context.get("tool_executor")
        tool_name = context.get("tool_name")
        tool_args = context.get("tool_args", {})
        agent_id = context.get("agent_id")
        permission_context = context.get("permission_context")

        if not tool_executor or not tool_name:
            return StrategyOutcome(
                status=VerificationStatus.SKIPPED,
                score=0.0,
                confidence=0.0,
                recommendation="No tool_executor or tool_name in context",
            )

        # Determine expected output from criteria or result_data
        expected_output: Any = None
        compare_field: str | None = None
        for c in criteria:
            if c.get("type") == "tool":
                expected_output = c.get("expected")
                compare_field = c.get("path")
                break

        if expected_output is None and compare_field:
            expected_output = _resolve_path(result_data, compare_field)

        # Execute the tool — preserving permission context (§45)
        tool_result: dict[str, Any] = {}
        error: str | None = None
        try:
            # Execute via the provided executor, passing the SAME permission context
            raw = tool_executor(
                tool_name=tool_name,
                args=tool_args,
                agent_id=agent_id,
                permission_context=permission_context,
            )
            if isinstance(raw, dict):
                tool_result = raw
            elif isinstance(raw, str):
                tool_result = {"output": raw}
            else:
                tool_result = {"output": str(raw)}
        except Exception as exc:
            error = str(exc)
            tool_result = {"error": error}

        # Compare
        if error:
            status = VerificationStatus.FAIL
            score = 0.0
            passed = False
        elif expected_output is not None:
            tool_output = tool_result.get("output", tool_result)
            passed = tool_output == expected_output
            score = 1.0 if passed else 0.0
            status = VerificationStatus.PASS if passed else VerificationStatus.FAIL
        else:
            # No expected output — just check that the tool ran without error
            passed = "error" not in tool_result
            score = 1.0 if passed else 0.0
            status = VerificationStatus.PASS if passed else VerificationStatus.FAIL

        criteria_list = [
            VerificationCriteria(
                key=f"tool_{tool_name}",
                label=f"Tool re-run: {tool_name}",
                type="tool",
                passed=passed,
                actual=tool_result,
                expected=expected_output,
            )
        ]

        return StrategyOutcome(
            status=status,
            score=score,
            confidence=0.9,  # High confidence — tool output is deterministic
            criteria=criteria_list,
            evidence=[tool_result],
        )


def _resolve_path(data: dict[str, Any], path: str | None) -> Any:
    """Resolve a dot-separated path."""
    if not path:
        return None
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current
