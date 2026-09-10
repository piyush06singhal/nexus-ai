"""Failure diagnosis (Phase 6, spec §19).

Heuristic, deterministic evidence-based rule mapping from error signals to a
structured :class:`FailureDiagnosis`. The diagnoser examines exception types,
execution status, tool call status, and error text to produce a category,
severity, retryability, recommended strategy, and confidence score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.recovery.taxonomy import FailureCategory, FailureSeverity, is_retryable
from app.recovery.types import FailureDiagnosis

# ── Signal-to-category mapping ────────────────────────────────────────────────

_EXCEPTION_CATEGORY_MAP: dict[str, tuple[FailureCategory, FailureSeverity]] = {
    # Timeouts
    "timeout": (FailureCategory.TIMEOUT, FailureSeverity.MEDIUM),
    "timedout": (FailureCategory.TIMEOUT, FailureSeverity.MEDIUM),
    "TimeoutError": (FailureCategory.TIMEOUT, FailureSeverity.MEDIUM),
    "asyncio.TimeoutError": (FailureCategory.TIMEOUT, FailureSeverity.MEDIUM),
    # Model failures
    "rate_limit": (FailureCategory.MODEL_FAILURE, FailureSeverity.LOW),
    "RateLimitError": (FailureCategory.MODEL_FAILURE, FailureSeverity.LOW),
    "context_length": (FailureCategory.MODEL_FAILURE, FailureSeverity.MEDIUM),
    "model_error": (FailureCategory.MODEL_FAILURE, FailureSeverity.MEDIUM),
    "APIError": (FailureCategory.MODEL_FAILURE, FailureSeverity.MEDIUM),
    "overloaded": (FailureCategory.MODEL_FAILURE, FailureSeverity.HIGH),
    # Tool failures
    "tool_error": (FailureCategory.TOOL_FAILURE, FailureSeverity.MEDIUM),
    "tool_timeout": (FailureCategory.TOOL_FAILURE, FailureSeverity.MEDIUM),
    "execution_error": (FailureCategory.TOOL_FAILURE, FailureSeverity.MEDIUM),
    # Permission
    "permission": (FailureCategory.PERMISSION_FAILURE, FailureSeverity.HIGH),
    "denied": (FailureCategory.PERMISSION_FAILURE, FailureSeverity.HIGH),
    "forbidden": (FailureCategory.PERMISSION_FAILURE, FailureSeverity.HIGH),
    "unauthorized": (FailureCategory.PERMISSION_FAILURE, FailureSeverity.HIGH),
    "access_denied": (FailureCategory.PERMISSION_FAILURE, FailureSeverity.HIGH),
    # Input/Output
    "validation": (FailureCategory.VALIDATION_FAILURE, FailureSeverity.LOW),
    "schema": (FailureCategory.VALIDATION_FAILURE, FailureSeverity.LOW),
    "malformed": (FailureCategory.INVALID_INPUT, FailureSeverity.LOW),
    "parse": (FailureCategory.INVALID_OUTPUT, FailureSeverity.LOW),
    "json": (FailureCategory.INVALID_OUTPUT, FailureSeverity.LOW),
    # System
    "connection": (FailureCategory.COMMUNICATION_FAILURE, FailureSeverity.MEDIUM),
    "network": (FailureCategory.COMMUNICATION_FAILURE, FailureSeverity.MEDIUM),
    "memory": (FailureCategory.RESOURCE_LIMIT, FailureSeverity.HIGH),
    "oom": (FailureCategory.RESOURCE_LIMIT, FailureSeverity.CRITICAL),
    "disk": (FailureCategory.RESOURCE_LIMIT, FailureSeverity.HIGH),
    # Dependency
    "import": (FailureCategory.DEPENDENCY_FAILURE, FailureSeverity.MEDIUM),
    "module": (FailureCategory.DEPENDENCY_FAILURE, FailureSeverity.MEDIUM),
    "missing": (FailureCategory.DEPENDENCY_FAILURE, FailureSeverity.MEDIUM),
}

# Strategy recommendations by category
_STRATEGY_RECOMMENDATIONS: dict[FailureCategory, str] = {
    FailureCategory.TIMEOUT: "retry_with_backoff",
    FailureCategory.MODEL_FAILURE: "retry_with_modified_input",
    FailureCategory.TOOL_FAILURE: "fallback_tool",
    FailureCategory.PERMISSION_FAILURE: "escalate",
    FailureCategory.VALIDATION_FAILURE: "retry_with_modified_input",
    FailureCategory.INVALID_INPUT: "retry_with_modified_input",
    FailureCategory.INVALID_OUTPUT: "retry_with_modified_input",
    FailureCategory.DEPENDENCY_FAILURE: "replan",
    FailureCategory.COMMUNICATION_FAILURE: "retry_with_backoff",
    FailureCategory.RESOURCE_LIMIT: "abort",
    FailureCategory.MEMORY_FAILURE: "abort",
    FailureCategory.VERIFICATION_FAILURE: "replan",
    FailureCategory.SYSTEM_FAILURE: "abort",
    FailureCategory.UNKNOWN: "retry",
}


@dataclass
class HeuristicDiagnoser:
    """Deterministic evidence-based failure diagnoser (spec §19).

    Examines error text, exception type, execution status, and tool call
    records to produce a structured :class:`FailureDiagnosis`.
    """

    def diagnose(
        self,
        error_text: str | None = None,
        exception_type: str | None = None,
        execution_status: str | None = None,
        tool_call_status: str | None = None,
        tool_call_result: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> FailureDiagnosis:
        """Diagnose a failure from observed signals.

        Args:
            error_text: Error message or traceback fragment.
            exception_type: Python exception class name.
            execution_status: Current execution status string.
            tool_call_status: Tool call result status (e.g., "error", "timeout").
            tool_call_result: Full tool call result dict.
            context: Additional context (agent_id, task_id, etc.).

        Returns:
            A structured :class:`FailureDiagnosis`.
        """
        signals = self._collect_signals(
            error_text,
            exception_type,
            execution_status,
            tool_call_status,
            tool_call_result,
            context,
        )

        category = self._classify_category(signals)
        severity = self._classify_severity(signals, category)
        root_cause = self._determine_root_cause(signals, category)
        retryable = is_retryable(category, severity)
        strategy = _STRATEGY_RECOMMENDATIONS.get(category, "retry")
        confidence = self._compute_confidence(signals)

        return FailureDiagnosis(
            execution_id=context.get("execution_id") if context else None,
            category=category.value,
            severity=severity.value,
            root_cause=root_cause,
            retryable=retryable,
            recommended_strategy=strategy,
            confidence=confidence,
            evidence=signals,
        )

    def _collect_signals(
        self,
        error_text: str | None,
        exception_type: str | None,
        execution_status: str | None,
        tool_call_status: str | None,
        tool_call_result: dict[str, Any] | None,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Collect all available signals into a single dict."""
        signals: dict[str, Any] = {
            "error_text": error_text,
            "exception_type": exception_type,
            "execution_status": execution_status,
            "tool_call_status": tool_call_status,
            "tool_call_result_status": (tool_call_result or {}).get("status"),
            "tool_call_result_error": (tool_call_result or {}).get("error"),
        }
        if context:
            signals["context"] = context
        return signals

    def _classify_category(self, signals: dict[str, Any]) -> FailureCategory:
        """Classify the failure category from signals."""
        # Check exception type first (most specific)
        exc_type = signals.get("exception_type", "") or ""
        for key, (cat, _) in _EXCEPTION_CATEGORY_MAP.items():
            if key.lower() in exc_type.lower():
                return cat

        # Check error text
        error_text = (signals.get("error_text") or "").lower()
        for key, (cat, _) in _EXCEPTION_CATEGORY_MAP.items():
            if key.lower() in error_text:
                return cat

        # Check tool call status
        tool_status = (signals.get("tool_call_status") or "").lower()
        if "timeout" in tool_status:
            return FailureCategory.TIMEOUT
        if "error" in tool_status or "denied" in tool_status:
            return FailureCategory.TOOL_FAILURE

        # Check execution status
        exec_status = (signals.get("execution_status") or "").lower()
        if "timeout" in exec_status:
            return FailureCategory.TIMEOUT
        if "error" in exec_status:
            return FailureCategory.MODEL_FAILURE

        return FailureCategory.UNKNOWN

    def _classify_severity(
        self,
        signals: dict[str, Any],
        category: FailureCategory,
    ) -> FailureSeverity:
        """Determine severity from signals and category."""
        # Check for critical signals
        error_text = (signals.get("error_text") or "").lower()
        if any(kw in error_text for kw in ("oom", "out of memory", "fatal", "critical")):
            return FailureSeverity.CRITICAL

        # Default severity by category
        _CATEGORY_SEVERITY: dict[FailureCategory, FailureSeverity] = {
            FailureCategory.TIMEOUT: FailureSeverity.MEDIUM,
            FailureCategory.MODEL_FAILURE: FailureSeverity.MEDIUM,
            FailureCategory.TOOL_FAILURE: FailureSeverity.MEDIUM,
            FailureCategory.PERMISSION_FAILURE: FailureSeverity.HIGH,
            FailureCategory.VALIDATION_FAILURE: FailureSeverity.LOW,
            FailureCategory.INVALID_INPUT: FailureSeverity.LOW,
            FailureCategory.INVALID_OUTPUT: FailureSeverity.LOW,
            FailureCategory.DEPENDENCY_FAILURE: FailureSeverity.MEDIUM,
            FailureCategory.COMMUNICATION_FAILURE: FailureSeverity.MEDIUM,
            FailureCategory.RESOURCE_LIMIT: FailureSeverity.HIGH,
            FailureCategory.SYSTEM_FAILURE: FailureSeverity.CRITICAL,
            FailureCategory.UNKNOWN: FailureSeverity.MEDIUM,
        }
        return _CATEGORY_SEVERITY.get(category, FailureSeverity.MEDIUM)

    def _determine_root_cause(
        self,
        signals: dict[str, Any],
        category: FailureCategory,
    ) -> str:
        """Extract or infer the root cause."""
        error = signals.get("error_text") or signals.get("tool_call_result_error") or ""
        if error:
            # Truncate long errors
            return error[:500]
        return f"Failure category: {category.value}"

    def _compute_confidence(self, signals: dict[str, Any]) -> float:
        """Compute confidence in the diagnosis."""
        # More signals = higher confidence
        non_empty = sum(1 for v in signals.values() if v is not None and v != "")
        total = len(signals)
        return round(non_empty / max(total, 1), 2)
