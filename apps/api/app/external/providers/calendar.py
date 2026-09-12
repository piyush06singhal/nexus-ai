"""Calendar provider — deterministic mock calendar (Phase 10).

Deterministic in-process calendar store keyed by integration slug. Capabilities:
list_events (LOW), get_event (LOW), create_event (MEDIUM), update_event (MEDIUM),
cancel_event (MEDIUM/HIGH-irreversible). Real CalDAV/OAuth calendar providers
are Phase 11 behind this same seam.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.models.external import (
    AuthMethod,
    IntegrationCategory,
    Reversibility,
    RiskLevel,
)
from app.external.types import (
    AuthContext,
    Capability,
    ExternalAuthFailure,
    ExternalCalendarEvent,
    ExternalNotFoundFailure,
    ExternalValidationFailure,
)

API_KEY_ENV_HINT = "INTEGRATION_CALENDAR_API_KEY"

_CALENDAR: dict[str, dict[str, ExternalCalendarEvent]] = {}


def _seed_calendar(slug: str) -> None:
    if slug in _CALENDAR:
        return
    now = datetime.now(UTC)
    _CALENDAR[slug] = {
        "evt-001": ExternalCalendarEvent(
            id="evt-001",
            title="Weekly product sync",
            start=(now + timedelta(hours=1)).isoformat(),
            end=(now + timedelta(hours=2)).isoformat(),
            attendees=["product@nexus.test", "eng@nexus.test"],
        ),
        "evt-002": ExternalCalendarEvent(
            id="evt-002",
            title="Marketing review",
            start=(now + timedelta(days=1, hours=3)).isoformat(),
            end=(now + timedelta(days=1, hours=4)).isoformat(),
            attendees=["marketing@nexus.test"],
        ),
    }


class CalendarProvider:
    """Deterministic calendar adapter over a mock calendar store."""

    slug = "calendar"
    name = "Calendar"
    category = IntegrationCategory.PRODUCTIVITY
    auth_type = AuthMethod.API_KEY
    description = "Deterministic calendar adapter over a mock calendar store (Phase 10)."

    def __init__(self) -> None:
        _seed_calendar(self.slug)

    def secrets_required(self) -> list[str]:
        return [API_KEY_ENV_HINT]

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="list_events",
                description="List calendar events in a window.",
                capability_type="read",
                risk_level=RiskLevel.LOW,
                input_schema={
                    "type": "object",
                    "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
                },
                reversibility=Reversibility.REVERSIBLE,
            ),
            Capability(
                name="get_event",
                description="Fetch a single event by id.",
                capability_type="read",
                risk_level=RiskLevel.LOW,
                input_schema={"type": "object", "properties": {"event_id": {"type": "string"}}},
                reversibility=Reversibility.REVERSIBLE,
            ),
            Capability(
                name="create_event",
                description="Create a calendar event with attendees.",
                capability_type="write",
                risk_level=RiskLevel.MEDIUM,
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "attendees": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "start", "end"],
                },
                reversibility=Reversibility.PARTIALLY_REVERSIBLE,
                supports_idempotency=True,
                required_permissions=["calendar:write"],
                required_scopes=["calendar:write"],
            ),
            Capability(
                name="update_event",
                description="Update event fields (title/time/attendees).",
                capability_type="write",
                risk_level=RiskLevel.MEDIUM,
                input_schema={
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "title": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["event_id"],
                },
                reversibility=Reversibility.PARTIALLY_REVERSIBLE,
                required_permissions=["calendar:write"],
            ),
            Capability(
                name="cancel_event",
                description="Cancel an event, notifying attendees.",
                capability_type="write",
                risk_level=RiskLevel.HIGH,
                input_schema={"type": "object", "properties": {"event_id": {"type": "string"}}},
                reversibility=Reversibility.IRREVERSIBLE,
                supports_idempotency=True,
                approval_required=True,
                required_permissions=["calendar:write"],
            ),
        ]

    def test(
        self, *, payload: dict[str, Any], auth: AuthContext, context: dict[str, Any]
    ) -> tuple[str, str]:
        if not auth.secrets.get("api_key"):
            raise ExternalAuthFailure("Calendar provider requires INTEGRATION_CALENDAR_API_KEY")
        return "connected", "Calendar reachable (mock)."

    def execute(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        auth: AuthContext,
        connection: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not auth.secrets.get("api_key"):
            raise ExternalAuthFailure("Calendar provider requires INTEGRATION_CALENDAR_API_KEY")
        if capability == "list_events":
            return {"events": [e.to_dict() for e in _CALENDAR[self.slug].values()]}
        if capability == "get_event":
            return {"event": _get(payload, self.slug)}
        if capability == "create_event":
            return {"event": _create(payload, self.slug)}
        if capability == "update_event":
            return {"event": _update(payload, self.slug)}
        if capability == "cancel_event":
            return {"event": _cancel(payload, self.slug)}
        raise ExternalValidationFailure(f"Unknown calendar capability {capability!r}")


def _get(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    event = _CALENDAR[slug].get(str(payload.get("event_id", "")))
    if event is None:
        raise ExternalNotFoundFailure(f"Event {payload.get('event_id')!r} not found")
    return event.to_dict()


def _create(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    title = str(payload.get("title", ""))
    start = str(payload.get("start", ""))
    end = str(payload.get("end", ""))
    if not title or not start or not end:
        raise ExternalValidationFailure("Event requires title, start and end")
    event_id = f"evt-{len(_CALENDAR[slug]) + 1:03d}"
    event = ExternalCalendarEvent(
        id=event_id,
        title=title,
        start=start,
        end=end,
        attendees=[str(a) for a in (payload.get("attendees") or [])],
    )
    _CALENDAR[slug][event_id] = event
    return event.to_dict()


def _update(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    event_id = str(payload.get("event_id", ""))
    event = _CALENDAR[slug].get(event_id)
    if event is None:
        raise ExternalNotFoundFailure(f"Event {event_id!r} not found")
    if "title" in payload:
        event.title = str(payload["title"])
    if "start" in payload:
        event.start = str(payload["start"])
    if "end" in payload:
        event.end = str(payload["end"])
    return event.to_dict()


def _cancel(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    event_id = str(payload.get("event_id", ""))
    event = _CALENDAR[slug].get(event_id)
    if event is None:
        raise ExternalNotFoundFailure(f"Event {event_id!r} not found")
    event.status = "cancelled"
    return event.to_dict()
