"""External verification helpers (Phase 10, §59).

Each helper verifies one *kind* of external side-effect through the existing
Phase 6 :class:`VerificationService` — none of these are a second verification
system. A helper confirms the side-effect deterministically from the outcome
the action returned (Phase 10: the mock providers confirm synchronously via a
read-back resource id / sent state), then records the pass through
``VerificationService.verify_data``.

Callers pass a :class:`VerificationService` (as ``svc``); the helpers return a
:class:`VerificationOutcome` exposing ``.verified`` (plus status/score/reason).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VerificationOutcome:
    """Result of an external-side-effect verification."""

    verified: bool
    expectation: str
    status: str = "confirmed"  # mirrors the underlying service status when recorded
    score: float = 0.0
    reason: str | None = None
    confirmed_via: str = "provider_readback"


# Verifier callables: (action result data) -> bool. In Phase 10 each mock
# provider exposes deterministic confirmation (e.g. ``get_issue`` after
# ``create_issue``, message status == "sent" after send).
Verifier = Callable[[dict[str, Any]], bool]


def _svc(svc: Any) -> Any:
    """Accept a VerificationService or a db Session and return a service."""
    if hasattr(svc, "verify_data"):
        return svc
    from app.services.verification_service import VerificationService

    return VerificationService(svc)


def verify_resource_created(
    svc: Any,
    result_data: dict[str, Any],
    resource_type: str | None = None,
    resource_id: str | None = None,
    *,
    risk_level: str = "low",
) -> VerificationOutcome:
    """Verify a resource was created (e.g. ``create_issue``)."""
    confirmed = bool(resource_id and _find_id(result_data, str(resource_id)))
    return _record(svc, result_data, "resource_created", risk_level, confirmed)


def verify_resource_updated(
    svc: Any,
    before: dict[str, Any],
    after: dict[str, Any],
    resource_type: str | None = None,
    resource_id: str | None = None,
    *,
    risk_level: str = "low",
) -> VerificationOutcome:
    """Verify a resource changed between two observed states."""
    confirmed = bool(
        resource_id
        and _find_id(before, str(resource_id))
        and _find_id(after, str(resource_id))
        and before != after
    )
    return _record(svc, after, "resource_updated", risk_level, confirmed)


def verify_resource_deleted(
    svc: Any,
    result_data: dict[str, Any],
    resource_type: str | None = None,
    resource_id: str | None = None,
    *,
    risk_level: str = "medium",
) -> VerificationOutcome:
    """Verify a resource reports a deleted state."""
    confirmed = bool(resource_id and _find_id(result_data, str(resource_id)))
    if confirmed and not _find_deleted(result_data):
        confirmed = False
    return _record(svc, result_data, "resource_deleted", risk_level, confirmed)


def verify_message_sent(
    svc: Any,
    result_data: dict[str, Any],
    message_id: str | None,
    *,
    risk_level: str = "high",
) -> VerificationOutcome:
    """Verify a message reached a sent state."""
    confirmed = bool(message_id and _find_with_status(result_data, str(message_id), "sent"))
    return _record(svc, result_data, "message_sent", risk_level, confirmed)


def verify_event_created(
    svc: Any,
    result_data: dict[str, Any],
    event_id: str | None,
    *,
    risk_level: str = "low",
) -> VerificationOutcome:
    """Verify an event resource was created."""
    confirmed = bool(event_id and _find_id(result_data, str(event_id)))
    return _record(svc, result_data, "event_created", risk_level, confirmed)


def verify_issue_created(
    svc: Any,
    result_data: dict[str, Any],
    issue_id: str | None,
    *,
    risk_level: str = "low",
) -> VerificationOutcome:
    """Verify an issue was created."""
    confirmed = bool(issue_id and _find_id(result_data, str(issue_id)))
    return _record(svc, result_data, "issue_created", risk_level, confirmed)


def verify_page_state(
    svc: Any,
    page: dict[str, Any],
    url: str | None = None,
    *,
    expected_title: str | None = None,
    risk_level: str = "low",
) -> VerificationOutcome:
    """Verify a page observation matches the requested URL/title."""
    confirmed = bool(url and page.get("url") == url)
    if confirmed and expected_title:
        confirmed = expected_title.lower() in str(page.get("title", "")).lower()
    return _record(svc, page, "page_state", risk_level, confirmed)


def verify_expected_text(
    svc: Any,
    text: Any,
    expected: str,
    *,
    risk_level: str = "low",
) -> VerificationOutcome:
    """Verify the result exposes expected text (bounded match)."""
    confirmed = bool(expected and expected.lower() in str(text).lower())
    data = {"text": str(text)} if not isinstance(text, dict) else text
    return _record(svc, data, "expected_text", risk_level, confirmed)


# ── Internals ──────────────────────────────────────────────────────────────


def _record(
    svc: Any,
    result_data: dict[str, Any],
    expectation: str,
    risk_level: str,
    confirmed: bool,
) -> VerificationOutcome:
    service = _svc(svc)
    reason: str | None = None
    status = "confirmed"
    score = 1.0 if confirmed else 0.0
    if confirmed and isinstance(result_data, dict):
        try:
            outcome = service.verify_data(
                result_data,
                policy=None,
                risk_level=risk_level,
                context={"expectation": expectation, "external": True},
            )
            status = (
                outcome.status.value if hasattr(outcome.status, "value") else str(outcome.status)
            )
            score = float(getattr(outcome, "score", 0.0) or 0.0)
            reason = outcome.reason
        except Exception as exc:  # noqa: BLE001 - verification never hides the outcome
            reason = str(exc)[:256]
    return VerificationOutcome(
        verified=confirmed,
        expectation=expectation,
        status=status,
        score=score,
        reason=reason,
        confirmed_via="provider_readback" if confirmed else "none",
    )


def _find_id(data: Any, resource_id: str) -> bool:
    """Whether a dict somewhere in *data* carries ``id == resource_id``."""
    if isinstance(data, dict):
        if str(data.get("id", "")) == resource_id:
            return True
        return any(_find_id(v, resource_id) for v in data.values())
    if isinstance(data, list):
        return any(_find_id(v, resource_id) for v in data)
    return False


def _find_with_status(data: Any, resource_id: str, status: str) -> bool:
    """Whether the dict with ``id == resource_id`` also reports *status*."""
    if isinstance(data, dict):
        if str(data.get("id", "")) == resource_id:
            return str(data.get("status", "")) == status
        return any(_find_with_status(v, resource_id, status) for v in data.values())
    if isinstance(data, list):
        return any(_find_with_status(v, resource_id, status) for v in data)
    return False


def _find_deleted(data: Any) -> bool:
    """Whether a dict marks a resource as deleted (flag or status)."""
    if isinstance(data, dict):
        if data.get("deleted") is True or str(data.get("status", "")) == "deleted":
            return True
        return any(_find_deleted(v) for v in data.values())
    if isinstance(data, list):
        return any(_find_deleted(v) for v in data)
    return False
