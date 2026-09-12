"""Webhook ingest for the external event layer (Phase 10 §36).

Inbound webhooks are *never* trusted commands. Each payload is validated
(signature, timestamp window, size cap, rate limit), de-duplicated by its
``X-NEXUS-Event-Id`` (ingest key), and stored as a normalized
:class:`ExternalEvent` with ``signature_status`` recorded. Nothing in the
payload is executed by this module — consuming layers decide whether an event
warrants follow-up, always through the standard external-action funnel.

Signature scheme (mirrors common provider webhook conventions):
- Header ``X-NEXUS-Signature: t=<unix-seconds>,v1=<sha256-hmac-hex>``
- HMAC key is ``settings.external_webhook_hmac_secret`` (operator env var).
- A timestamp older than ``WEBHOOK_TIMESTAMP_WINDOW_SECONDS`` is rejected to
  bound replay windows (independent of the ingest-id dedupe).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.external import (
    ExternalEvent,
    ExternalEventSource,
    SignatureStatus,
    VerificationStatusExternal,
)
from app.external.api.rate_limit import RateLimiter
from app.external.events import ExternalEventLogger, ExternalEvents
from app.external.idempotency import event_already_ingested, event_ingest_key
from app.external.integration import IntegrationService

WEBHOOK_TIMESTAMP_WINDOW_SECONDS = 300

_rate_limiter = RateLimiter(default_per_minute=settings.external_rate_limit_per_minute)

# Header names
H_SIGNATURE = "x-nexus-signature"
H_EVENT_ID = "x-nexus-event-id"
H_TIMESTAMP = "x-nexus-timestamp"


class WebhookError(ValueError):
    """Rejected webhook: maps to a 4xx by the router."""

    def __init__(
        self, message: str, *, status_code: int = 400, code: str = "webhook_rejected"
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def extract_signature_components(signature: str | None) -> dict[str, str]:
    """Parse ``t=...;v1=...`` (provider-style) into a mapping."""
    components: dict[str, str] = {}
    if not signature:
        return components
    for part in signature.split(","):
        if "=" in part:
            key, _, value = part.partition("=")
            components[key.strip()] = value.strip()
    return components


def compute_hmac(payload_bytes: bytes, secret: str, timestamp: str) -> str:
    message = f"{timestamp}.".encode() + payload_bytes
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


class WebhookService:
    """Validate, dedupe, rate-limit and persist an inbound webhook event."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = ExternalEventLogger(db)
        self._integrations = IntegrationService(db)

    def ingest(
        self,
        *,
        company_id: UUID,
        provider: str,
        event_type: str,
        payload: dict[str, Any],
        signature: str | None = None,
        event_id: str | None = None,
        timestamp: str | None = None,
    ) -> ExternalEvent:
        """Validate and store one inbound webhook event.

        Raises :class:`WebhookError` for rejection (mapped to 4xx/413/503 by
        the router). External event records are never treated as commands.
        """
        if not settings.external_webhook_hmac_secret:
            raise WebhookError(
                "Webhooks are not enabled for this deployment",
                status_code=503,
                code="webhooks_disabled",
            )

        # 1. Provider/integration identity — the company must actually own an
        #    integration of this provider before we accept events from it.
        integrations = [i for i in self._integrations.list_(company_id) if i.provider == provider]
        if not integrations:
            raise WebhookError(
                f"No {provider} integration for company {company_id}",
                status_code=404,
                code="unknown_provider",
            )
        integration = integrations[0]

        # 2. Rate limit per (provider|company) before any parsing work.
        key = f"{provider}|{company_id}"
        if not _rate_limiter.allow(key):
            raise WebhookError(
                "Rate limit exceeded for webhook delivery", status_code=429, code="rate_limited"
            )

        # 3. Payload size cap.
        encoded = len(json.dumps(payload).encode("utf-8"))
        if encoded > settings.max_webhook_payload_bytes:
            raise WebhookError(
                "Webhook payload exceeds size limit", status_code=413, code="payload_too_large"
            )

        # 4. Signature verification (+ embedded timestamp window).
        sig_status, provider_ts = self._verify_signature(signature, event_id, timestamp, payload)

        # 5. Replay/dedupe on the ingest id (independent of signature).
        ingest_id = event_ingest_key("webhook", event_id or provider_ts)
        if event_id and event_already_ingested(self._db, source="webhook", ingest_id=event_id):
            self._events.log(
                action=ExternalEvents.WEBHOOK_REPLAY_BLOCKED,
                company_id=company_id,
                target_type="external_event",
                details={"provider": provider, "event_id": event_id},
            )
            raise WebhookError(
                "Duplicate webhook event already ingested", status_code=409, code="duplicate_event"
            )

        # 6. Persist as a normalized, never-trusted event.
        event = ExternalEvent(
            source=ExternalEventSource.WEBHOOK,
            integration_id=integration.id,
            company_id=company_id,
            event_type=event_type or "unknown",
            payload=json.dumps(payload, default=str)[: settings.max_webhook_payload_bytes],
            payload_size=encoded,
            timestamp=_parse_provider_timestamp(provider_ts),
            verification_status=VerificationStatusExternal.NOT_VERIFIED,
            correlation_id=None,
            signature_status=sig_status,
            ingest_id=event_id or ingest_id,
        )
        self._db.add(event)
        self._db.commit()
        self._db.refresh(event)
        self._events.log(
            action=ExternalEvents.WEBHOOK_RECEIVED,
            company_id=company_id,
            target_type="external_event",
            target_id=event.id,
            details={"provider": provider, "event_type": event_type, "signature": sig_status.value},
        )
        return event

    def _verify_signature(
        self,
        signature: str | None,
        event_id: str | None,
        header_timestamp: str | None,
        payload: dict[str, Any],
    ) -> tuple[SignatureStatus, str | None]:
        """Return (signature_status, provider timestamp) for the payload."""
        secret = settings.external_webhook_hmac_secret
        components = extract_signature_components(signature)
        ts = components.get("t") or header_timestamp
        sig = components.get("v1")
        if not sig:
            self._events.log(
                action=ExternalEvents.WEBHOOK_SIGNATURE_INVALID,
                company_id=None,
                target_type="external_event",
                details={"reason": "missing_signature"},
            )
            raise WebhookError(
                "Missing webhook signature", status_code=401, code="signature_missing"
            )

        # Timestamp window — reject stale payloads (replay bound).
        try:
            provider_ts = float(ts)
        except (TypeError, ValueError):
            raise WebhookError(  # noqa: B904
                "Invalid webhook timestamp", status_code=401, code="invalid_timestamp"
            )
        if abs(time.time() - provider_ts) > WEBHOOK_TIMESTAMP_WINDOW_SECONDS:
            self._events.log(
                action=ExternalEvents.WEBHOOK_REPLAY_BLOCKED,
                company_id=None,
                target_type="external_event",
                details={"reason": "stale_timestamp"},
            )
            raise WebhookError(
                "Webhook timestamp outside allowed window", status_code=401, code="stale_timestamp"
            )

        payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        expected = compute_hmac(payload_bytes, secret, str(int(provider_ts)))
        if not hmac.compare_digest(expected, sig):
            self._events.log(
                action=ExternalEvents.WEBHOOK_SIGNATURE_INVALID,
                company_id=None,
                target_type="external_event",
                details={"reason": "signature_mismatch"},
            )
            raise WebhookError(
                "Invalid webhook signature", status_code=401, code="signature_invalid"
            )
        return SignatureStatus.VERIFIED, str(int(provider_ts))


def _parse_provider_timestamp(ts: str | None) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC)
    except (TypeError, ValueError):
        return None


def _stored_event(db: Session, event: ExternalEvent) -> dict[str, Any]:
    """Serializer used by the router (parsed JSON payload)."""
    payload = None
    if event.payload:
        try:
            payload = json.loads(event.payload)
        except ValueError:
            payload = event.payload
    return {
        "id": str(event.id),
        "source": event.source.value,
        "integration_id": str(event.integration_id) if event.integration_id else None,
        "company_id": str(event.company_id) if event.company_id else None,
        "event_type": event.event_type,
        "payload": payload,
        "payload_size": event.payload_size,
        "timestamp": event.timestamp,
        "verification_status": event.verification_status.value,
        "correlation_id": event.correlation_id,
        "signature_status": event.signature_status.value,
        "ingest_id": event.ingest_id,
        "received_at": event.received_at,
    }


def list_events(db: Session, company_id: UUID, *, limit: int = 50) -> list[ExternalEvent]:
    return list(
        db.execute(
            sa_select(ExternalEvent)
            .where(ExternalEvent.company_id == company_id)
            .order_by(ExternalEvent.received_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
