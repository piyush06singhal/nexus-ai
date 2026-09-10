"""Retry safety classifier (Phase 6, spec §15–§16, §45–§47).

Determines whether a recovery action (retry, re-run, etc.) is safe to execute.
Safety is evaluated in terms of:
- Side-effect classification (read-only / reversible / irreversible / high-risk)
- Idempotency (idempotent / non-idempotent / unknown)
- Permission preservation (recovery never broadens permissions)

Recovery never broadens permissions (§45). Idempotency gates retry (§47).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SideEffectKind(StrEnum):
    """Classification of operation side effects."""

    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"
    HIGH_RISK = "high_risk"


class IdempotencyClass(StrEnum):
    """Idempotency classification for retry safety."""

    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"
    UNKNOWN = "unknown"


@dataclass
class SafetyVerdict:
    """Result of a safety evaluation."""

    safe_to_retry: bool
    reason: str
    side_effect: SideEffectKind = SideEffectKind.READ_ONLY
    idempotency: IdempotencyClass = IdempotencyClass.UNKNOWN
    preconditions: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "safe_to_retry": self.safe_to_retry,
            "reason": self.reason,
            "side_effect": self.side_effect.value,
            "idempotency": self.idempotency.value,
            "preconditions": self.preconditions or [],
        }


# ── Side-effect rules ─────────────────────────────────────────────────────────

# Tools that are known to have side effects
_SIDE_EFFECT_MAP: dict[str, SideEffectKind] = {
    # Read-only
    "web_search": SideEffectKind.READ_ONLY,
    "read_file": SideEffectKind.READ_ONLY,
    "search": SideEffectKind.READ_ONLY,
    "get": SideEffectKind.READ_ONLY,
    "fetch": SideEffectKind.READ_ONLY,
    # Reversible
    "write_file": SideEffectKind.REVERSIBLE,
    "update": SideEffectKind.REVERSIBLE,
    "create": SideEffectKind.REVERSIBLE,
    # Irreversible (but generally safe)
    "send_email": SideEffectKind.IRREVERSIBLE,
    "post_webhook": SideEffectKind.IRREVERSIBLE,
    # High-risk
    "delete": SideEffectKind.HIGH_RISK,
    "execute": SideEffectKind.HIGH_RISK,
    "run": SideEffectKind.HIGH_RISK,
    "deploy": SideEffectKind.HIGH_RISK,
    "publish": SideEffectKind.HIGH_RISK,
}

# Tool call result statuses that indicate non-safe for blind retry
_UNSAFE_STATUSES = frozenset({"denied", "timeout", "error", "permission_error"})


@dataclass
class RetrySafety:
    """Deterministic safety classifier for recovery actions (§15–§16)."""

    # Tools that are known to be idempotent (safe to re-run)
    idempotent_tools: set[str] | None = None

    def __post_init__(self):
        if self.idempotent_tools is None:
            self.idempotent_tools = set()

    def evaluate(
        self,
        tool_name: str | None = None,
        tool_result_status: str | None = None,
        operation_type: str | None = None,
        permission_context: Any = None,
        previous_attempts: int = 0,
    ) -> SafetyVerdict:
        """Evaluate whether a retry is safe.

        Args:
            tool_name: Name of the tool that was called.
            tool_result_status: Status of the tool call result.
            operation_type: Type of operation (read, write, execute, etc.).
            permission_context: The permission context for the original call.
            previous_attempts: How many retry attempts have already been made.

        Returns:
            A :class:`SafetyVerdict` indicating safety.
        """
        # 1. Check result status — certain statuses are never safe for blind retry
        if tool_result_status and tool_result_status.lower() in _UNSAFE_STATUSES:
            return SafetyVerdict(
                safe_to_retry=False,
                reason=f"Tool result status '{tool_result_status}' is not safe for blind retry",
                side_effect=self._classify_side_effect(tool_name, operation_type),
                idempotency=IdempotencyClass.NON_IDEMPOTENT,
            )

        # 2. Check idempotency
        idempotency = self._classify_idempotency(tool_name)

        # 3. Check side effects
        side_effect = self._classify_side_effect(tool_name, operation_type)

        # 4. High-risk operations are never safe for automatic retry
        if side_effect == SideEffectKind.HIGH_RISK:
            return SafetyVerdict(
                safe_to_retry=False,
                reason=f"High-risk operation '{tool_name}' requires human approval",
                side_effect=side_effect,
                idempotency=idempotency,
            )

        # 5. Non-idempotent + irreversible → not safe for automatic retry
        if (
            idempotency == IdempotencyClass.NON_IDEMPOTENT
            and side_effect == SideEffectKind.IRREVERSIBLE
        ):
            return SafetyVerdict(
                safe_to_retry=False,
                reason="Non-idempotent irreversible operation cannot be safely retried",
                side_effect=side_effect,
                idempotency=idempotency,
            )

        # 6. Unknown idempotency + previous attempts > 0 → increasingly unsafe
        if idempotency == IdempotencyClass.UNKNOWN and previous_attempts > 0:
            return SafetyVerdict(
                safe_to_retry=False,
                reason=f"Unknown idempotency after {previous_attempts} attempts — escalate",
                side_effect=side_effect,
                idempotency=idempotency,
            )

        # 7. Permission denied → never retry (§45: no permission escalation)
        if tool_result_status and "permission" in tool_result_status.lower():
            return SafetyVerdict(
                safe_to_retry=False,
                reason="Permission denied — recovery cannot broaden permissions (§45)",
                side_effect=side_effect,
                idempotency=idempotency,
            )

        # Safe to retry
        preconditions: list[str] = []
        if idempotency == IdempotencyClass.IDEMPOTENT:
            preconditions.append("idempotency guaranteed")
        if side_effect == SideEffectKind.READ_ONLY:
            preconditions.append("read-only operation")
        if previous_attempts > 0:
            preconditions.append(f"attempt {previous_attempts + 1}")

        return SafetyVerdict(
            safe_to_retry=True,
            reason="Retry is safe within safety bounds",
            side_effect=side_effect,
            idempotency=idempotency,
            preconditions=preconditions,
        )

    def _classify_idempotency(self, tool_name: str | None) -> IdempotencyClass:
        """Classify idempotency of a tool."""
        if not tool_name:
            return IdempotencyClass.UNKNOWN
        if tool_name in (self.idempotent_tools or set()):
            return IdempotencyClass.IDEMPOTENT
        # Known idempotent tools
        _IDEMPOTENT_TOOLS = frozenset(
            {"get", "read", "search", "fetch", "list", "query", "read_file"}
        )
        if tool_name.lower() in _IDEMPOTENT_TOOLS:
            return IdempotencyClass.IDEMPOTENT
        return IdempotencyClass.UNKNOWN

    def _classify_side_effect(
        self,
        tool_name: str | None,
        operation_type: str | None,
    ) -> SideEffectKind:
        """Classify side effects of a tool."""
        # Check explicit operation type first
        if operation_type:
            op_map = {
                "read": SideEffectKind.READ_ONLY,
                "write": SideEffectKind.REVERSIBLE,
                "create": SideEffectKind.REVERSIBLE,
                "update": SideEffectKind.REVERSIBLE,
                "delete": SideEffectKind.HIGH_RISK,
                "execute": SideEffectKind.HIGH_RISK,
            }
            result = op_map.get(operation_type.lower())
            if result:
                return result

        # Check tool name
        if tool_name:
            for pattern, kind in _SIDE_EFFECT_MAP.items():
                if pattern in tool_name.lower():
                    return kind

        return SideEffectKind.READ_ONLY  # Default to safest assumption
