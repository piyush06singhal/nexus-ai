"""Idempotency for external actions and webhook ingest (Phase 10, §8/§36).

An external action is keyed by ``(company_id, integration_id, capability,
idempotency_key)``; once an action with that key reaches a *terminal* outcome,
the same key is either refused (duplicate SUCCEEDED) or clearly flagged.
Webhooks are keyed by ``(source, ingest_id)``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.external import ExternalAction, ExternalEvent

_TERMINAL_STATUS = {"succeeded", "failed", "cancelled", "blocked"}


def normalize_key(value: str | None) -> str | None:
    """Normalize a caller-supplied idempotency key to a stable form."""
    if not value:
        return None
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def generate_operation_id(prefix: str = "extop") -> str:
    """Generate a stable external operation identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


class IdempotencyGuard:
    """Dedupe + look up terminal external actions by idempotency key."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def find_terminal(
        self,
        *,
        company_id: UUID,
        integration_id: UUID,
        capability: str,
        idempotency_key: str | None,
    ) -> ExternalAction | None:
        """Return a prior terminal action for the same key, if any."""
        key = normalize_key(idempotency_key)
        if key is None:
            return None
        stmt = (
            select(ExternalAction)
            .where(
                ExternalAction.company_id == company_id,
                ExternalAction.integration_id == integration_id,
                ExternalAction.capability == capability,
                ExternalAction.idempotency_key == key,
            )
            .order_by(ExternalAction.created_at.desc())
        )
        for action in list(self._db.execute(stmt).scalars().all()):
            if action.status.value in _TERMINAL_STATUS:
                return action
        return None

    def is_duplicate(
        self,
        *,
        company_id: UUID,
        integration_id: UUID,
        capability: str,
        idempotency_key: str | None,
    ) -> bool:
        terminal = self.find_terminal(
            company_id=company_id,
            integration_id=integration_id,
            capability=capability,
            idempotency_key=idempotency_key,
        )
        return terminal is not None and terminal.status.value == "succeeded"


def event_ingest_key(source: str, ingest_id: str | None) -> str | None:
    if not ingest_id:
        return None
    return hashlib.sha256(f"{source}:{ingest_id}".encode()).hexdigest()


def event_already_ingested(db: Session, *, source: str, ingest_id: str | None) -> bool:
    if not ingest_id:
        return False
    stmt = select(ExternalEvent).where(
        ExternalEvent.source == source, ExternalEvent.ingest_id == ingest_id
    )
    return db.scalar(stmt) is not None


def payload_fingerprint(payload: dict[str, Any]) -> str:
    """Stable hash of a JSON payload (ordering-insensitive)."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
