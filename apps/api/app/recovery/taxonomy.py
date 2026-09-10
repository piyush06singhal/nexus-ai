"""Failure taxonomy (Phase 6, spec §14).

Structured failure classification used throughout the recovery engine to
determine retryability, strategy selection, and escalation behavior.
"""

from __future__ import annotations

from enum import StrEnum


class FailureCategory(StrEnum):
    """Structured failure taxonomy (spec §14)."""

    VALIDATION_FAILURE = "validation_failure"
    MODEL_FAILURE = "model_failure"
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    PERMISSION_FAILURE = "permission_failure"
    INVALID_INPUT = "invalid_input"
    INVALID_OUTPUT = "invalid_output"
    DEPENDENCY_FAILURE = "dependency_failure"
    MEMORY_FAILURE = "memory_failure"
    COMMUNICATION_FAILURE = "communication_failure"
    RESOURCE_LIMIT = "resource_limit"
    VERIFICATION_FAILURE = "verification_failure"
    SYSTEM_FAILURE = "system_failure"
    UNKNOWN = "unknown"


class FailureSeverity(StrEnum):
    """Severity of a failure (spec §14)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Categories that are always retryable
_RETRYABLE_CATEGORIES = frozenset(
    {
        FailureCategory.TIMEOUT,
        FailureCategory.TOOL_FAILURE,
        FailureCategory.MODEL_FAILURE,
        FailureCategory.COMMUNICATION_FAILURE,
        FailureCategory.DEPENDENCY_FAILURE,
    }
)

# Categories that are never retryable (require different resolution)
_NON_RETRYABLE_CATEGORIES = frozenset(
    {
        FailureCategory.PERMISSION_FAILURE,
        FailureCategory.SYSTEM_FAILURE,
        FailureCategory.RESOURCE_LIMIT,
    }
)

# Severity → max auto-recovery attempts
_SEVERITY_MAX_ATTEMPTS: dict[FailureSeverity, int] = {
    FailureSeverity.LOW: 3,
    FailureSeverity.MEDIUM: 2,
    FailureSeverity.HIGH: 1,
    FailureSeverity.CRITICAL: 0,  # Must escalate
}


def is_retryable(category: FailureCategory, severity: FailureSeverity) -> bool:
    """Determine if a failure category is generally retryable."""
    if category in _NON_RETRYABLE_CATEGORIES:
        return False
    if category in _RETRYABLE_CATEGORIES:
        return True
    # For unknown/other categories: retryable if severity is LOW or MEDIUM
    return severity in (FailureSeverity.LOW, FailureSeverity.MEDIUM)


def max_auto_attempts(severity: FailureSeverity) -> int:
    """Max automatic recovery attempts for a given severity."""
    return _SEVERITY_MAX_ATTEMPTS.get(severity, 1)
