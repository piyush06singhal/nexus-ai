"""External failure → Phase 6 recovery mapping (Phase 10, §60).

No second taxonomy: :func:`classify_external_failure` maps an
:class:`ExternalProviderError` (stable ``error_code``) to the existing Phase 6
:class:`FailureCategory`/:class:`FailureSeverity`, and :func:`recovery_strategy`
reuses the Phase 6 retry vocabulary. Retries are always idempotency-protected
— a non-idempotent capability is only auto-retried when the caller supplied an
``idempotency_key``/operation id, otherwise it escalates.
"""

from __future__ import annotations

from app.db.models.external import Reversibility
from app.external.types import (
    ExternalAuthFailure,
    ExternalNotFoundFailure,
    ExternalPermissionFailure,
    ExternalProviderError,
    ExternalRateLimitFailure,
    ExternalSystemFailure,
    ExternalTimeoutFailure,
    ExternalValidationFailure,
)
from app.recovery.taxonomy import FailureCategory, FailureSeverity

# error_code → (FailureCategory, FailureSeverity default)
_CODE_MAP: dict[str, tuple[FailureCategory, FailureSeverity]] = {
    "auth_failed": (FailureCategory.PERMISSION_FAILURE, FailureSeverity.HIGH),
    "permission_denied": (FailureCategory.PERMISSION_FAILURE, FailureSeverity.MEDIUM),
    "http_429": (FailureCategory.RESOURCE_LIMIT, FailureSeverity.MEDIUM),
    "timeout": (FailureCategory.TIMEOUT, FailureSeverity.HIGH),
    "validation_failed": (FailureCategory.VALIDATION_FAILURE, FailureSeverity.MEDIUM),
    "not_found": (FailureCategory.VALIDATION_FAILURE, FailureSeverity.LOW),
    "transport_error": (FailureCategory.SYSTEM_FAILURE, FailureSeverity.MEDIUM),
    "system_error": (FailureCategory.SYSTEM_FAILURE, FailureSeverity.HIGH),
    "http_5xx": (FailureCategory.SYSTEM_FAILURE, FailureSeverity.MEDIUM),
    "external_error": (FailureCategory.TOOL_FAILURE, FailureSeverity.MEDIUM),
}


def classify_external_failure(error_code: str) -> tuple[FailureCategory, FailureSeverity]:
    """Map a stable external error code onto the Phase 6 taxonomy."""
    if error_code in _CODE_MAP:
        category, severity = _CODE_MAP[error_code]
        return category, severity
    # Numeric HTTP codes beyond the named ones.
    if error_code.startswith("http_"):
        code = int(error_code.removeprefix("http_"))
        if 500 <= code <= 599:
            return FailureCategory.SYSTEM_FAILURE, FailureSeverity.MEDIUM
        if code == 429:
            return FailureCategory.RESOURCE_LIMIT, FailureSeverity.MEDIUM
        if code in (401, 403):
            return FailureCategory.PERMISSION_FAILURE, FailureSeverity.HIGH
        if code in (408, 504):
            return FailureCategory.TIMEOUT, FailureSeverity.HIGH
        if 400 <= code <= 499:
            return FailureCategory.VALIDATION_FAILURE, FailureSeverity.MEDIUM
    return FailureCategory.TOOL_FAILURE, FailureSeverity.MEDIUM


def retryable(
    *,
    error_code: str,
    supports_idempotency: bool,
    has_idempotency_key: bool,
    reversibility: Reversibility,
) -> tuple[bool, int]:
    """Decide whether to auto-retry and the bounded attempt count.

    A failure is auto-retried only when (a) it is a transient failure class AND
    (b) replaying it is provably safe: the capability either carries a caller
    idempotency key or is fully reversible. Otherwise it escalates (attempts=0).
    """
    category, severity = classify_external_failure(error_code)
    retry_classes = {
        FailureCategory.TIMEOUT,
        FailureCategory.SYSTEM_FAILURE,
        FailureCategory.RESOURCE_LIMIT,
    }
    if category not in retry_classes:
        return False, 0
    safe_to_replay = (supports_idempotency and has_idempotency_key) or reversibility in {
        Reversibility.REVERSIBLE,
        Reversibility.PARTIALLY_REVERSIBLE,
    }
    if not safe_to_replay:
        return False, 0
    from app.recovery.taxonomy import max_auto_attempts

    max_attempts = min(max_auto_attempts(severity), 2)
    return True, max_attempts


def strategy_for(category: FailureCategory) -> str:
    """Recovery strategy label for the attempt trace (Phase 6 vocabulary)."""
    return {
        FailureCategory.TIMEOUT: "retry_with_backoff",
        FailureCategory.SYSTEM_FAILURE: "retry_with_backoff",
        FailureCategory.RESOURCE_LIMIT: "retry_with_backoff",
        FailureCategory.PERMISSION_FAILURE: "escalate",
        FailureCategory.VALIDATION_FAILURE: "replan",
        FailureCategory.TOOL_FAILURE: "fallback",
    }.get(category, "escalate")


def classify_exception(exc: Exception) -> str:
    """Return a stable error_code for an arbitrary exception (defensive)."""
    if isinstance(exc, ExternalRateLimitFailure):
        return exc.error_code
    if isinstance(exc, ExternalTimeoutFailure):
        return exc.error_code
    if isinstance(exc, ExternalAuthFailure):
        return exc.error_code
    if isinstance(exc, ExternalPermissionFailure):
        return exc.error_code
    if isinstance(exc, ExternalValidationFailure):
        return exc.error_code
    if isinstance(exc, ExternalNotFoundFailure):
        return exc.error_code
    if isinstance(exc, ExternalSystemFailure):
        return exc.error_code
    if isinstance(exc, ExternalProviderError):
        return exc.error_code
    return "external_error"
