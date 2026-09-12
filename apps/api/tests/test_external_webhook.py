"""Phase 10 webhook ingestion tests — valid/invalid signature, replay,
malformed/oversized payload, duplicate event, rate limit (§75 Webhook).
"""

from __future__ import annotations

import time
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app

_counter = 0

_SECRET = "webhook-shared-secret-123"


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Webhook Co {_counter}", description="unit")


def _enable_webhooks(monkeypatch, secret: str = _SECRET) -> str:
    """Turn on the Hmac secret (defaults empty -> router returns 503)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "external_webhook_hmac_secret", secret)
    return secret


def _email_integration(db: Session, company_id: UUID) -> None:
    """The company must own an ``email`` integration before we accept events."""
    from app.external.integration import IntegrationService

    IntegrationService(db).create(company_id=company_id, provider="email", name="Email")


def _setup(monkeypatch, db: Session):
    """Create a company owning an email integration, with webhooks enabled."""
    company = _company(db)
    _enable_webhooks(monkeypatch)
    _email_integration(db, company.id)
    return company


def _signature(secret: str, payload: dict, timestamp: float | None = None) -> str:
    from app.external.api.auth import build_webhook_signature

    return build_webhook_signature(secret, payload, timestamp=timestamp)


def _client_with_db(db: Session) -> TestClient:
    """Test client that reuses the provided db session (avoids sqlite lock)."""
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _url(company_id: UUID) -> str:
    return f"/api/v1/webhooks/{company_id}/events/email"


_PAYLOAD = {"event_type": "message_received", "data": {"id": "msg-1"}}


class TestWebhookSignature:
    def test_valid_hmac_sha256_signature_accepted(self, db: Session, monkeypatch) -> None:
        company = _setup(monkeypatch, db)
        signature = _signature(_SECRET, _PAYLOAD)

        r = _client_with_db(db).post(
            _url(company.id),
            json=_PAYLOAD,
            headers={"X-Nexus-Signature": signature},
        )
        assert r.status_code == 202, r.text
        assert r.json()["received"] is True
        assert r.json()["signature_status"] == "verified"

    def test_invalid_signature_rejected(self, db: Session, monkeypatch) -> None:
        company = _setup(monkeypatch, db)
        r = _client_with_db(db).post(
            _url(company.id),
            json=_PAYLOAD,
            headers={"X-Nexus-Signature": "sha256=invalid_signature_here"},
        )
        assert r.status_code == 401, r.text
        assert "signature" in r.json()["detail"].lower()

    def test_missing_signature_rejected_when_required(self, db: Session, monkeypatch) -> None:
        company = _setup(monkeypatch, db)
        r = _client_with_db(db).post(_url(company.id), json=_PAYLOAD)
        assert r.status_code == 401, r.text
        assert "signature" in r.json()["detail"].lower()

    def test_unknown_provider_rejected(self, db: Session, monkeypatch) -> None:
        """A company that owns no integration of this provider is refused."""
        company = _setup(monkeypatch, db)
        signature = _signature(_SECRET, _PAYLOAD)
        r = _client_with_db(db).post(
            f"/api/v1/webhooks/{company.id}/events/gcalendar",
            json=_PAYLOAD,
            headers={"X-Nexus-Signature": signature},
        )
        assert r.status_code == 404, r.text


class TestWebhookReplayProtection:
    def test_duplicate_event_id_rejected(self, db: Session, monkeypatch) -> None:
        company = _setup(monkeypatch, db)
        signature = _signature(_SECRET, _PAYLOAD)

        # First delivery with an explicit ingest id -> accepted.
        r = _client_with_db(db).post(
            _url(company.id),
            json=_PAYLOAD,
            headers={"X-Nexus-Signature": signature, "X-Nexus-Event-Id": "evt-001"},
        )
        assert r.status_code == 202, r.text

        # Replay of the same event id -> 409 duplicate.
        r = _client_with_db(db).post(
            _url(company.id),
            json=_PAYLOAD,
            headers={"X-Nexus-Signature": signature, "X-Nexus-Event-Id": "evt-001"},
        )
        assert r.status_code == 409, r.text
        assert "duplicate" in r.json()["detail"].lower()

    def test_timestamp_outside_window_rejected(self, db: Session, monkeypatch) -> None:
        company = _setup(monkeypatch, db)
        # The signature itself must embed the stale timestamp (the ingestion
        # layer uses the signature's t= value, not the header).
        old = time.time() - 600
        signature = _signature(_SECRET, _PAYLOAD, timestamp=old)

        r = _client_with_db(db).post(
            _url(company.id),
            json=_PAYLOAD,
            headers={"X-Nexus-Signature": signature},
        )
        assert r.status_code == 401, r.text
        assert "timestamp" in r.json()["detail"].lower()


class TestWebhookPayloadValidation:
    def test_malformed_json_rejected(self, db: Session, monkeypatch) -> None:
        company = _setup(monkeypatch, db)
        r = _client_with_db(db).post(
            _url(company.id),
            content="{ not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400, r.text

    def test_oversized_payload_rejected(self, db: Session, monkeypatch) -> None:
        company = _setup(monkeypatch, db)
        large_payload = {"event_type": "message_received", "data": {"x": "x" * 20000}}
        signature = _signature(_SECRET, large_payload)

        r = _client_with_db(db).post(
            _url(company.id),
            json=large_payload,
            headers={"X-Nexus-Signature": signature},
        )
        assert r.status_code == 413, r.text
        assert "payload" in r.json()["detail"].lower()

    def test_event_persisted_to_external_events(self, db: Session, monkeypatch) -> None:
        from app.db.models.external import ExternalEvent, ExternalEventSource

        company = _setup(monkeypatch, db)
        signature = _signature(_SECRET, _PAYLOAD)

        r = _client_with_db(db).post(
            _url(company.id), json=_PAYLOAD, headers={"X-Nexus-Signature": signature}
        )
        assert r.status_code == 202, r.text

        events = db.query(ExternalEvent).filter(ExternalEvent.company_id == company.id).all()
        assert len(events) == 1
        assert events[0].source == ExternalEventSource.WEBHOOK
        assert events[0].event_type == "message_received"
        assert events[0].signature_status.value == "verified"


class TestWebhookRateLimit:
    def test_rate_limit_enforced(self, db: Session, monkeypatch) -> None:
        from app.external.api.rate_limit import RateLimiter

        company = _setup(monkeypatch, db)
        # The module-level limiter is a singleton created at import; replace it
        # with a fresh 2/min limiter for this test.
        import app.external.webhook as webhook_module

        webhook_module._rate_limiter = RateLimiter(default_per_minute=2)

        for i in range(3):
            payload = {"event_type": "message_received", "data": {"id": f"msg-{i}"}}
            # Provide unique event_id to avoid dedupe collision on timestamp-based ingest_id
            event_id = f"evt-rate-{i}"
            signature = _signature(_SECRET, payload)
            r = _client_with_db(db).post(
                _url(company.id),
                json=payload,
                headers={"X-Nexus-Signature": signature, "X-Nexus-Event-Id": event_id},
            )
            if i < 2:
                assert r.status_code == 202, f"Request {i} failed: {r.text}"
            else:
                assert r.status_code == 429, f"Request {i} should be rate limited: {r.text}"


class TestWebhookUnauthenticatedNeverTrusted:
    def test_unauthenticated_webhook_never_creates_trusted_command(
        self, db: Session, monkeypatch
    ) -> None:
        """Unauthenticated payloads are never trusted commands (§86 Rule 10)."""
        from app.db.models.external import ExternalEvent

        company = _setup(monkeypatch, db)
        payload = {"event_type": "admin_delete_all", "data": {}}

        # No signature header -> 401 before any persistence.
        r = _client_with_db(db).post(_url(company.id), json=payload)
        assert r.status_code == 401, r.text

        events = db.query(ExternalEvent).filter(ExternalEvent.company_id == company.id).all()
        assert len(events) == 0
