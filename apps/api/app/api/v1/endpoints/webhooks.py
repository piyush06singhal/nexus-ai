"""Webhook inbound endpoints (Phase 10 §36).

``POST /{company_id}/webhooks/{provider}/events`` validates a signed payload
(X-Nexus-Signature, timestamp window), size-caps and rate-limits it, and
persists a normalized ``external_events`` row. A webhook is never a trusted
command — nothing is executed here, so an unverified payload cannot change
policy, permissions, secrets, or trigger external actions by itself.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.company import Company
from app.db.session import get_db
from app.external.webhook import (
    WebhookError,
    WebhookService,
)

router = APIRouter(tags=["external-webhooks"], prefix="/webhooks")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.post(
    "/{company_id}/events/{provider}",
    status_code=202,
    summary="Ingest a signed webhook event (stored, never executed)",
)
async def receive_webhook(
    company_id: UUID,
    provider: str,
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008
    x_nexus_signature: str | None = Header(default=None, alias="X-Nexus-Signature"),
    x_nexus_event_id: str | None = Header(default=None, alias="X-Nexus-Event-Id"),
    x_nexus_timestamp: str | None = Header(default=None, alias="X-Nexus-Timestamp"),
) -> dict[str, Any]:
    _company_or_404(db, company_id)
    if not settings.external_webhook_hmac_secret:
        raise HTTPException(
            status_code=503,
            detail="Webhooks are not enabled — no NEXUS webhook secret configured",
        )
    body = await request.body()
    try:
        awaited = body.decode("utf-8")
        import json

        payload = json.loads(awaited) if awaited else {}
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON webhook payload") from exc

    event_type = payload.get("event_type") or payload.get("type") or "unknown"
    try:
        event = WebhookService(db).ingest(
            company_id=company_id,
            provider=provider,
            event_type=str(event_type),
            payload=payload,
            signature=x_nexus_signature,
            event_id=x_nexus_event_id,
            timestamp=x_nexus_timestamp,
        )
    except WebhookError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    return {
        "received": True,
        "event_id": str(event.id),
        "event_type": event.event_type,
        "signature_status": event.signature_status.value,
        "verification_status": event.verification_status.value,
    }
