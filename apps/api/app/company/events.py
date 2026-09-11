"""AI Company Layer — organizational event / timeline logger.

Records organizational changes (company created, department created, employee
added, goal created, decision approved, alert generated, …) with actor, target,
action, outcome, and correlation id so the full history is auditable and
traceable back to company / department / employee. This is the single audit +
timeline mechanism for Phase 8.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.company import OrgEvent


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


class OrgEventLogger:
    """Persist and query organizational audit/timeline events."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def log(
        self,
        *,
        actor: str,
        action: str,
        company_id: UUID | None = None,
        target_type: str | None = None,
        target_id: UUID | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        outcome: str | None = None,
    ) -> OrgEvent:
        """Record a single organizational event (not committed by default)."""
        event = OrgEvent(
            actor=actor,
            action=action,
            company_id=company_id,
            target_type=target_type,
            target_id=target_id,
            details=_dumps(details),
            correlation_id=correlation_id,
            outcome=outcome,
        )
        self._db.add(event)
        self._db.flush()
        return event

    def query(
        self,
        *,
        company_id: UUID | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: UUID | None = None,
        actor: str | None = None,
        limit: int = 100,
    ) -> list[OrgEvent]:
        """Query events, newest first, with optional filters."""
        from sqlalchemy import select

        stmt = select(OrgEvent).order_by(OrgEvent.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(OrgEvent.company_id == company_id)
        if action is not None:
            stmt = stmt.where(OrgEvent.action == action)
        if target_type is not None:
            stmt = stmt.where(OrgEvent.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(OrgEvent.target_id == target_id)
        if actor is not None:
            stmt = stmt.where(OrgEvent.actor == actor)
        stmt = stmt.limit(limit)
        return list(self._db.execute(stmt).scalars().all())

    def to_dict(self, event: OrgEvent) -> dict[str, Any]:
        """Serialize an event using the API schema field names."""
        return {
            "id": str(event.id),
            "company_id": str(event.company_id) if event.company_id else None,
            "actor": event.actor,
            "action": event.action,
            "target_type": event.target_type,
            "target_id": str(event.target_id) if event.target_id else None,
            "details": json.loads(event.details) if event.details else None,
            "outcome": event.outcome,
            # kept in both forms: correlation_id for internal, recorded_at time
            "correlation_id": (str(event.correlation_id) if event.correlation_id else None),
            "created_at": event.created_at,
        }

    def timeline(self, company_id: UUID, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return the human-facing timeline for a company."""
        events = self.query(company_id=company_id, limit=limit)
        return [self.to_dict(e) for e in events]

    def timeline_for_target(
        self, target_type: str, target_id: UUID, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return events filtered to a specific target (e.g. a department)."""
        events = self.query(target_type=target_type, target_id=target_id, limit=limit)
        return [self.to_dict(e) for e in events]
