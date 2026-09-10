"""Deterministic verification strategy (Phase 6, spec §4).

Checks literals (expected == actual), field presence, non-empty output, and
value-in-enum constraints.  Fully deterministic — no LLM calls, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.verification.types import StrategyOutcome as _StrategyOutcome
from app.verification.types import VerificationCriteria, VerificationStatus


class StrategyOutcome(_StrategyOutcome):
    """Local alias so ``DeterministicVerifier`` doesn't leak the base type."""


@runtime_checkable
class DeterministicVerifier(Protocol):
    """Protocol for the deterministic verification strategy."""

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        """Run deterministic checks on *result_data*.

        Args:
            result_data: The structured output produced by the agent/tool.
            criteria: Optional list of verification criteria to check.
            context: Optional execution context (unused by deterministic).

        Returns:
            A :class:`StrategyOutcome` with the aggregate verdict.
        """


@dataclass
class DefaultDeterministicVerifier:
    """Default implementation of deterministic verification.

    Supported criteria types:
        * ``presence`` — the ``path`` key exists in ``result_data``
        * ``equality`` — ``result_data[path] == expected``
        * ``nonempty`` — the value at ``path`` is truthy and non-empty
        * ``type_check`` — ``isinstance(result_data[path], expected_type)``
        * ``enum_value`` — ``result_data[path] in expected_values``
    """

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        criteria = criteria or []
        checked: list[VerificationCriteria] = []

        for c in criteria:
            ctype = c.get("type", "presence")
            key = c.get("key", c.get("path", "unknown"))
            label = c.get("label", key)
            path = c.get("path", c.get("key"))
            expected = c.get("expected")

            actual = _resolve_path(result_data, path)

            if ctype == "presence":
                passed = path is not None and _path_exists(result_data, path)
                checked.append(
                    VerificationCriteria(
                        key=key,
                        label=label,
                        type=ctype,
                        passed=passed,
                        actual=actual,
                        expected="present" if expected is None else expected,
                    )
                )
            elif ctype == "equality":
                passed = actual == expected
                checked.append(
                    VerificationCriteria(
                        key=key,
                        label=label,
                        type=ctype,
                        passed=passed,
                        actual=actual,
                        expected=expected,
                    )
                )
            elif ctype == "nonempty":
                passed = bool(actual)
                checked.append(
                    VerificationCriteria(
                        key=key,
                        label=label,
                        type=ctype,
                        passed=passed,
                        actual=actual,
                        expected="non-empty",
                    )
                )
            elif ctype == "type_check":
                passed = isinstance(actual, expected) if expected is not False else False
                checked.append(
                    VerificationCriteria(
                        key=key,
                        label=label,
                        type=ctype,
                        passed=passed,
                        actual=type(actual).__name__ if actual is not None else "None",
                        expected=str(expected) if expected is not None else "None",
                    )
                )
            elif ctype == "enum_value":
                passed = actual in (expected or [])
                checked.append(
                    VerificationCriteria(
                        key=key,
                        label=label,
                        type=ctype,
                        passed=passed,
                        actual=actual,
                        expected=expected,
                    )
                )
            else:
                # Not a criterion owned by this strategy — skip it rather than
                # flagging UNCERTAIN (each strategy only evaluates its own type).
                continue

        return _aggregate(checked)


def _path_exists(data: dict[str, Any], path: str | None) -> bool:
    """Check whether a dot-separated path exists in *data*."""
    if not path:
        return False
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False
    return True


def _resolve_path(data: dict[str, Any], path: str | None) -> Any:
    """Resolve a dot-separated path in *data*, returning ``None`` on miss."""
    if not path:
        return None
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _aggregate(criteria: list[VerificationCriteria]) -> StrategyOutcome:
    """Compute an aggregate score/confidence/status from checked criteria."""
    if not criteria:
        return StrategyOutcome(
            status=VerificationStatus.SKIPPED,
            score=0.0,
            confidence=0.0,
        )

    n = len(criteria)
    passed_count = sum(1 for c in criteria if c.passed is True)
    failed_count = sum(1 for c in criteria if c.passed is False)
    uncertain_count = sum(1 for c in criteria if c.passed is None)

    score = passed_count / n if n else 0.0

    # Confidence: 1.0 if all passed deterministically, lower if there's ambiguity.
    if uncertain_count > 0:
        confidence = passed_count / n
    elif failed_count > 0:
        confidence = 1.0  # We're certain it failed
    else:
        confidence = 1.0  # All passed

    if failed_count > 0 and passed_count > 0:
        status = VerificationStatus.PARTIAL
    elif failed_count > 0:
        status = VerificationStatus.FAIL
    elif uncertain_count > 0:
        status = VerificationStatus.UNCERTAIN
    else:
        status = VerificationStatus.PASS

    return StrategyOutcome(
        status=status,
        score=score,
        confidence=confidence,
        criteria=criteria,
        evidence=[c.to_dict() for c in criteria],
    )
