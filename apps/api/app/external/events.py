"""External Integrations — event names + a thin logger.

The single audit path stays :class:`app.company.events.OrgEventLogger`
(Phase 8); this module only centralizes the external event-name vocabulary and
offers a small wrapper so every external service records company-scoped events
consistently. No second event store.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger


class ExternalEvents:
    """Event-name constants for the external integration layer."""

    # Integrations / connections
    INTEGRATION_CREATED = "integration_created"
    INTEGRATION_UPDATED = "integration_updated"
    INTEGRATION_DELETED = "integration_deleted"
    CONNECTION_CREATED = "connection_created"
    CONNECTION_TESTED = "connection_tested"
    CONNECTION_REVOKED = "connection_revoked"
    # Actions
    EXTERNAL_ACTION_REQUESTED = "external_action_requested"
    EXTERNAL_ACTION_AUTO = "external_action_auto"
    EXTERNAL_ACTION_APPROVAL_REQUIRED = "external_action_approval_required"
    EXTERNAL_ACTION_EXECUTED = "external_action_executed"
    EXTERNAL_ACTION_VERIFIED = "external_action_verified"
    EXTERNAL_ACTION_FAILED = "external_action_failed"
    EXTERNAL_ACTION_RECOVERED = "external_action_recovered"
    EXTERNAL_ACTION_BLOCKED = "external_action_blocked"
    EXTERNAL_ACTION_CANCELLED = "external_action_cancelled"
    EXTERNAL_ACTION_DUPLICATE_BLOCKED = "external_action_duplicate_blocked"
    # Browser / computer
    BROWSER_SESSION_CREATED = "browser_session_created"
    BROWSER_SESSION_ACTIVE = "browser_session_active"
    BROWSER_SESSION_PAUSED = "browser_session_paused"
    BROWSER_SESSION_TERMINATED = "browser_session_terminated"
    BROWSER_ACTION = "browser_action"
    COMPUTER_SESSION_CREATED = "computer_session_created"
    COMPUTER_SESSION_ACTIVE = "computer_session_active"
    COMPUTER_SESSION_PAUSED = "computer_session_paused"
    COMPUTER_SESSION_TERMINATED = "computer_session_terminated"
    COMPUTER_ACTION = "computer_action"
    # Security
    SSRF_BLOCKED = "ssrf_blocked"
    DOMAIN_BLOCKED = "domain_blocked"
    PROMPT_INJECTION_BLOCKED = "prompt_injection_blocked"
    EXFILTRATION_BLOCKED = "exfiltration_blocked"
    # Webhooks
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_SIGNATURE_INVALID = "webhook_signature_invalid"
    WEBHOOK_REPLAY_BLOCKED = "webhook_replay_blocked"


class ExternalEventLogger:
    """Record external events through the shared Phase 8 event log."""

    def __init__(self, db: Session) -> None:
        self._events = OrgEventLogger(db)

    def log(
        self,
        *,
        action: str,
        company_id: UUID | None = None,
        actor: str = "system",
        target_type: str | None = None,
        target_id: UUID | None = None,
        details: dict[str, Any] | None = None,
        outcome: str = "success",
        correlation_id: UUID | None = None,
    ) -> None:
        self._events.log(
            actor=actor,
            action=action,
            company_id=company_id,
            target_type=target_type,
            target_id=target_id,
            details=details,
            outcome=outcome,
            correlation_id=correlation_id,
        )
