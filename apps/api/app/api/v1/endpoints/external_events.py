"""External event feed endpoints (Phase 10 §49).

Read-only, company-scoped view of normalized external events (webhook ingest
and integration-triggered events). Events are *records*, never commands —
they carry a ``signature_status`` and a ``NOT_VERIFIED`` verification state
until a consuming layer verifies a side-effect.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.models.external import ExternalEvent
from app.db.session import get_db
from app.external.webhook import list_events
from app.schemas.external import ExternalEventRead

router = APIRouter(tags=["external-events"], prefix="/external-events")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _event_to_read(row: ExternalEvent) -> ExternalEventRead:
    return ExternalEventRead(
        id=row.id,
        source=row.source,
        integration_id=row.integration_id,
        company_id=row.company_id,
        event_type=row.event_type,
        payload=_loads(row.payload),
        payload_size=row.payload_size,
        timestamp=row.timestamp,
        verification_status=row.verification_status,
        correlation_id=row.correlation_id,
        signature_status=row.signature_status,
        ingest_id=row.ingest_id,
        received_at=row.received_at,
    )


def _loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return value


@router.get(
    "/{company_id}",
    response_model=list[ExternalEventRead],
    summary="List external events for a company",
)
def list_events_endpoint(
    company_id: UUID,
    source: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ExternalEventRead]:
    _company_or_404(db, company_id)
    rows = list_events(db, company_id, limit=limit)
    if source:
        rows = [r for r in rows if (r.source.value if r.source else None) == source]
    return [_event_to_read(r) for r in rows]


@router.get(
    "/{company_id}/{event_id}",
    response_model=ExternalEventRead,
    summary="Get one external event (404 isolated per company)",
)
def get_event(
    company_id: UUID,
    event_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ExternalEventRead:
    _company_or_404(db, company_id)
    row = db.get(ExternalEvent, event_id)
    if row is None or row.company_id != company_id:
        raise HTTPException(status_code=404, detail="External event not found")
    return _event_to_read(row)
