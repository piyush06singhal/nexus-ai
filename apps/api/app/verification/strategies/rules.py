"""Rules verification strategy (Phase 6, spec §7).

Evaluates a config list of ``{field/path, op, expected, label}`` rules against
the result data using a **safe, non-executable** operator vocabulary:

    eq, ne, gt, gte, lt, lte, contains, in, not_in, nonempty, type, required

Arbitrary ``eval``/executable rule bodies are explicitly rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.verification.types import StrategyOutcome as _StrategyOutcome
from app.verification.types import VerificationCriteria, VerificationStatus


class StrategyOutcome(_StrategyOutcome):
    """Local alias."""


# ── Safe operator registry ────────────────────────────────────────────────────


def _op_eq(actual: Any, expected: Any) -> bool:
    return actual == expected


def _op_ne(actual: Any, expected: Any) -> bool:
    return actual != expected


def _op_gt(actual: Any, expected: Any) -> bool:
    return actual is not None and actual > expected


def _op_gte(actual: Any, expected: Any) -> bool:
    return actual is not None and actual >= expected


def _op_lt(actual: Any, expected: Any) -> bool:
    return actual is not None and actual < expected


def _op_lte(actual: Any, expected: Any) -> bool:
    return actual is not None and actual <= expected


def _op_contains(actual: Any, expected: Any) -> bool:
    if actual is None:
        return False
    if isinstance(actual, str):
        return expected in actual
    if isinstance(actual, (list, set, tuple, dict)):
        return expected in actual
    return False


def _op_in(actual: Any, expected: Any) -> bool:
    if expected is None:
        return False
    return actual in expected


def _op_not_in(actual: Any, expected: Any) -> bool:
    if expected is None:
        return True
    return actual not in expected


def _op_nonempty(actual: Any, expected: Any = None) -> bool:
    if actual is None:
        return False
    if isinstance(actual, str):
        return len(actual) > 0
    if isinstance(actual, (list, dict, set, tuple)):
        return len(actual) > 0
    return bool(actual)


def _op_type(actual: Any, expected: Any) -> bool:
    """Check that actual is of the named type (string)."""
    _TYPE_MAP: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "str": str,
        "number": (int, float),
        "integer": int,
        "int": int,
        "float": float,
        "boolean": bool,
        "bool": bool,
        "list": list,
        "array": list,
        "dict": dict,
        "object": dict,
    }
    t = _TYPE_MAP.get(str(expected).lower())
    if t is None:
        return True
    return isinstance(actual, t)


def _op_required(actual: Any, expected: Any = None) -> bool:
    """Pass if the field was present (actual is not the sentinel)."""
    return actual is not _MISSING


_SENTINEL = object()
_MISSING = object()


_SAFE_OPS: dict[str, Any] = {
    "eq": _op_eq,
    "ne": _op_ne,
    "gt": _op_gt,
    "gte": _op_gte,
    "lt": _op_lt,
    "lte": _op_lte,
    "contains": _op_contains,
    "in": _op_in,
    "not_in": _op_not_in,
    "nonempty": _op_nonempty,
    "type": _op_type,
    "required": _op_required,
}

# Operators explicitly rejected for safety (never execute)
_BLOCKED_OPS = frozenset({"eval", "exec", "call", "lambda", "import"})


def _resolve_path(data: dict[str, Any], path: str | None) -> Any:
    """Resolve a dot-separated path, returning _MISSING if not found."""
    if not path:
        return _MISSING
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


@dataclass
class Rule:
    """A single verification rule."""

    field_path: str
    op: str
    expected: Any = None
    label: str = ""

    def __post_init__(self):
        if self.op in _BLOCKED_OPS:
            raise ValueError(f"Blocked operator '{self.op}' — not permitted for safety")
        if self.op not in _SAFE_OPS:
            raise ValueError(f"Unknown operator '{self.op}'. Safe ops: {sorted(_SAFE_OPS)}")


@runtime_checkable
class RuleVerifier(Protocol):
    """Protocol for the rules verification strategy."""

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        """Evaluate rules against result_data."""


@dataclass
class DefaultRuleVerifier:
    """Default implementation.

    Rules are supplied via ``criteria`` entries with ``type="rule"``:
        {key, type: "rule", label, path, op, expected}
    Or via ``context["rules"]`` as a list of dicts.
    """

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        context = context or {}
        criteria = criteria or []

        rules: list[Rule] = []

        for c in criteria:
            if c.get("type") == "rule":
                rules.append(
                    Rule(
                        field_path=c.get("path", c.get("field_path", c.get("key", ""))),
                        op=c.get("op", "eq"),
                        expected=c.get("expected"),
                        label=c.get("label", c.get("key", "rule")),
                    )
                )

        ctx_rules = context.get("rules", [])
        for r in ctx_rules:
            if isinstance(r, dict) and r.get("op") in _SAFE_OPS:
                rules.append(
                    Rule(
                        field_path=r.get("field_path", r.get("path", r.get("key", ""))),
                        op=r["op"],
                        expected=r.get("expected"),
                        label=r.get("label", r.get("key", "rule")),
                    )
                )

        if not rules:
            return StrategyOutcome(
                status=VerificationStatus.SKIPPED,
                score=0.0,
                confidence=0.0,
            )

        checked: list[VerificationCriteria] = []

        for rule in rules:
            actual = _resolve_path(result_data, rule.field_path)
            op_fn = _SAFE_OPS[rule.op]

            try:
                if rule.op == "required":
                    passed = op_fn(actual)
                elif rule.op == "nonempty":
                    passed = op_fn(actual)
                else:
                    passed = op_fn(actual, rule.expected)
            except Exception:
                passed = False

            checked.append(
                VerificationCriteria(
                    key=rule.field_path,
                    label=rule.label or f"{rule.field_path} {rule.op}",
                    type="rule",
                    passed=passed,
                    actual=actual if actual is not _MISSING else "<missing>",
                    expected=rule.expected,
                )
            )

        n = len(checked)
        passed_count = sum(1 for c in checked if c.passed is True)
        score = passed_count / n if n else 0.0
        failed = any(c.passed is False for c in checked)
        status = VerificationStatus.FAIL if failed else VerificationStatus.PASS

        return StrategyOutcome(
            status=status,
            score=score,
            confidence=1.0,
            criteria=checked,
            evidence=[c.to_dict() for c in checked],
        )
