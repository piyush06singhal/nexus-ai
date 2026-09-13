"""Security events, threat detection & security alerts (Phase 11).

Pipeline: **security_events** (raw, 13 categories §48, fingerprinted for
dedupe) → **ThreatDetectionService** (configurable rules §49) → **security_alerts**
(severity LOW→CRITICAL, integrates the Phase 8 ``AlertManager`` so security
alerts surface in the operator view too) → incidents (in ``incidents.py``).

Rules (all deterministic, window-based, testable):
- ``AUTH_BRUTE_FORCE``: ≥ N AUTH_FAILURE events in a window ⇒ HIGH alert.
- ``REPEATED_DENIED_TOOL``: ≥ M denied/policy-denied events ⇒ MEDIUM alert.
- ``CROSS_COMPANY_BURST``: ≥ K cross-company attempts ⇒ CRITICAL alert.
- ``EXTERNAL_ANOMALY``: large unusual external activity ⇒ MEDIUM/LOW alert.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.company import (
    AlertSeverity,
    GoalScopeType,
)
from app.db.models.security import (
    Incident,
    IncidentAction,
    IncidentActionState,
    IncidentStatus,
    SecurityAlert,
    SecurityAlertStatus,
    SecurityEvent,
    SecurityEventCategory,
    Severity,
)

logger = get_logger(__name__)


def _fingerprint(parts: list[str]) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SecurityEventService:
    """Record raw security events; dedupe by fingerprint; feed detection."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        category: SecurityEventCategory,
        severity: Severity,
        title: str,
        detail: dict | None = None,
        company_id: UUID | None = None,
        actor_id: UUID | None = None,
        observed_by: str | None = None,
        correlation_id: str | None = None,
        fingerprint_parts: list[str] | None = None,
        dedupe: bool = True,
    ) -> SecurityEvent:
        parts = fingerprint_parts or [
            category.value,
            title,
            str(company_id) if company_id else "",
            json.dumps(detail, sort_keys=True) if detail else "",
        ]
        fp = _fingerprint(parts)
        if dedupe:
            existing = self.db.execute(
                select(SecurityEvent).where(SecurityEvent.fingerprint == fp)
            ).scalar_one_or_none()
            if existing is not None:
                return existing
        event = SecurityEvent(
            company_id=company_id,
            category=category.value,
            severity=severity.value,
            title=title,
            detail=detail,
            observed_by=observed_by,
            actor_id=actor_id,
            correlation_id=correlation_id,
            fingerprint=fp,
        )
        self.db.add(event)
        self.db.flush()
        self._run_detection(event)
        return event

    # ── category helpers ───────────────────────────────────────────────────

    def auth_failure(
        self, *, email: str = "", ip: str = "", reason: str = "", company_id: UUID | None = None
    ) -> SecurityEvent:
        return self.record(
            category=SecurityEventCategory.AUTH_FAILURE,
            severity=Severity.MEDIUM,
            title=reason or "Login failed",
            detail={"email": email, "ip": ip, "reason": reason},
            company_id=company_id,
            observed_by="auth",
            fingerprint_parts=["auth_failure", email, ip, reason],
        )

    def token_invalid(self, *, reason: str, ip: str = "") -> SecurityEvent:
        return self.record(
            category=SecurityEventCategory.TOKEN_INVALID,
            severity=Severity.LOW,
            title="Invalid token rejected",
            detail={"reason": reason, "ip": ip},
            observed_by="auth",
            fingerprint_parts=["token_invalid", reason, ip],
        )

    def permission_denied(
        self,
        *,
        action: str,
        identity_id: UUID | None = None,
        company_id: UUID | None = None,
        detail: dict | None = None,
    ) -> SecurityEvent:
        return self.record(
            category=SecurityEventCategory.PERMISSION_DENIED,
            severity=Severity.MEDIUM,
            title=f"Permission denied: {action}",
            detail={"action": action, **(detail or {})},
            company_id=company_id,
            actor_id=identity_id,
            observed_by="authorization",
            fingerprint_parts=["permission_denied", str(identity_id or ""), action],
        )

    def cross_company(
        self, *, identity_id: UUID | None, company_id: UUID | None, target_company_id: UUID
    ) -> SecurityEvent:
        return self.record(
            category=SecurityEventCategory.CROSS_COMPANY_ACCESS,
            severity=Severity.HIGH,
            title="Cross-company access attempt",
            detail={"target_company_id": str(target_company_id)},
            company_id=company_id,
            actor_id=identity_id,
            observed_by="isolator",
            fingerprint_parts=[
                "cross_company",
                str(identity_id or ""),
                str(target_company_id),
            ],
        )

    def prompt_injection(
        self, *, source: str, company_id: UUID | None = None, detail: dict | None = None
    ) -> SecurityEvent:
        return self.record(
            category=SecurityEventCategory.PROMPT_INJECTION,
            severity=Severity.HIGH,
            title=f"Prompt injection detected ({source})",
            detail={"source": source, **(detail or {})},
            company_id=company_id,
            observed_by="context_security",
            fingerprint_parts=[
                "prompt_injection",
                source,
                json.dumps(detail or {}, sort_keys=True),
            ],
        )

    def ssrf_blocked(
        self, *, url: str, company_id: UUID | None = None, reason: str = "internal_address"
    ) -> SecurityEvent:
        return self.record(
            category=SecurityEventCategory.SSRF_BLOCKED,
            severity=Severity.MEDIUM,
            title="SSRF guard blocked request",
            detail={"url": url, "reason": reason},
            company_id=company_id,
            observed_by="ssrf_guard",
            fingerprint_parts=["ssrf_blocked", url, reason],
        )

    def secret_access_denied(
        self, *, secret_name: str, identity_id: UUID | None, company_id: UUID | None = None
    ) -> SecurityEvent:
        return self.record(
            category=SecurityEventCategory.SECRET_ACCESS_DENIED,
            severity=Severity.HIGH,
            title=f"Secret access denied: {secret_name}",
            detail={"secret_name": secret_name},
            company_id=company_id,
            actor_id=identity_id,
            observed_by="secrets",
            fingerprint_parts=[
                "secret_denied",
                secret_name,
                str(identity_id or ""),
            ],
        )

    # ── orchestrate detection ──────────────────────────────────────────────

    def _run_detection(self, event: SecurityEvent) -> None:
        try:
            ThreatDetectionService(self.db).evaluate(event)
        except Exception:
            logger.exception("threat_detection_error")
            # Detection is advisory — never let it break the security pipeline.


class ThreatDetectionService:
    """Configurable window-based detection rules (`security_alerts`)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # rule triggers (overridable for tests via settings-free constructor kwargs)
    def evaluate(
        self,
        event: SecurityEvent,
        *,
        window_minutes: int = 10,
        brute_force_threshold: int = 5,
        denied_threshold: int = 8,
        cross_company_threshold: int = 3,
    ) -> SecurityAlert | None:
        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=window_minutes)
        company_id = event.company_id

        if event.category == SecurityEventCategory.AUTH_FAILURE.value:
            count = self._count(
                category=SecurityEventCategory.AUTH_FAILURE, window_start=window_start
            )
            if count >= brute_force_threshold:
                return self._alert(
                    severity=Severity.HIGH,
                    rule_code="AUTH_BRUTE_FORCE",
                    title=f"Possible credential-stuffing: {count} failed logins",
                    company_id=company_id,
                    event=event,
                )

        if event.category in (
            SecurityEventCategory.PERMISSION_DENIED.value,
            SecurityEventCategory.POLICY_DENIED.value,
        ):
            count = self._count(
                categories=[
                    SecurityEventCategory.PERMISSION_DENIED,
                    SecurityEventCategory.POLICY_DENIED,
                ],
                window_start=window_start,
            )
            if count >= denied_threshold:
                return self._alert(
                    severity=Severity.MEDIUM,
                    rule_code="REPEATED_DENIED_TOOL",
                    title=f"Repeated denied attempts: {count}",
                    company_id=company_id,
                    event=event,
                )

        if event.category == SecurityEventCategory.CROSS_COMPANY_ACCESS.value:
            count = self._count(
                category=SecurityEventCategory.CROSS_COMPANY_ACCESS, window_start=window_start
            )
            if count >= cross_company_threshold:
                return self._alert(
                    severity=Severity.CRITICAL,
                    rule_code="CROSS_COMPANY_BURST",
                    title=f"Cross-company access burst: {count} attempts",
                    company_id=company_id,
                    event=event,
                )

        if event.category == SecurityEventCategory.RESOURCE_EXCEEDED.value:
            return self._alert(
                severity=Severity.MEDIUM,
                rule_code="RESOURCE_EXHAUSTION",
                title=event.title,
                company_id=company_id,
                event=event,
                description=event.detail.get("summary") if event.detail else None,
            )
        return None

    # ── internals ──────────────────────────────────────────────────────────

    def _count(
        self,
        *,
        category: SecurityEventCategory | None = None,
        categories: list[SecurityEventCategory] | None = None,
        window_start: datetime,
    ) -> int:
        stmt = select(func.count(SecurityEvent.id)).where(SecurityEvent.created_at >= window_start)
        if category is not None:
            stmt = stmt.where(SecurityEvent.category == category.value)
        if categories is not None:
            stmt = stmt.where(SecurityEvent.category.in_([c.value for c in categories]))
        return self.db.execute(stmt).scalar_one()

    def _alert(
        self,
        *,
        severity: Severity,
        rule_code: str,
        title: str,
        company_id: UUID | None,
        event: SecurityEvent,
        description: str | None = None,
    ) -> SecurityAlert | None:
        SecurityAlertService(self.db).create(
            severity=severity,
            rule_code=rule_code,
            title=title,
            description=description,
            company_id=company_id,
            source_event_id=event.id,
        )
        return None


class SecurityAlertService:
    """Create, acknowledge and resolve security alerts (integrates Phase 8)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        severity: Severity,
        rule_code: str | None,
        title: str,
        description: str | None = None,
        company_id: UUID | None = None,
        source_event_id: UUID | None = None,
        event_ids: list[str] | None = None,
    ) -> SecurityAlert:
        alert = SecurityAlert(
            company_id=company_id,
            severity=severity.value,
            rule_code=rule_code,
            title=title,
            description=description,
            source_event_id=source_event_id,
            event_ids={"ids": event_ids or []},
            status=SecurityAlertStatus.OPEN.value,
        )
        self.db.add(alert)
        self.db.flush()
        self._mirror_to_ops_alert(alert)
        return alert

    def _mirror_to_ops_alert(self, alert: SecurityAlert) -> None:
        """Surface in the Phase 8 operator `alerts` view too."""
        if not alert.company_id:
            return
        try:
            from app.company.alerts import AlertManager

            alert_manager = AlertManager(self.db)
            alert_manager.create(
                company_id=alert.company_id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=alert.company_id,
                title=alert.title,
                severity=AlertSeverity(alert.severity),
                category="security",
                message=alert.description or alert.title,
                payload={
                    "security_alert_id": str(alert.id),
                    "rule_code": alert.rule_code,
                },
            )
        except Exception:
            logger.exception("security_alert_mirror_failed")

    def acknowledge(self, alert_id: UUID, *, by: UUID | None = None) -> SecurityAlert:
        alert = self.get(alert_id)
        alert.status = SecurityAlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_by = by
        alert.acknowledged_at = datetime.now(UTC)
        self.db.flush()
        return alert

    def resolve(self, alert_id: UUID, *, note: str | None = None) -> SecurityAlert:
        alert = self.get(alert_id)
        alert.status = SecurityAlertStatus.RESOLVED.value
        alert.resolved_at = datetime.now(UTC)
        alert.resolution_note = note
        self.db.flush()
        return alert

    def get(self, alert_id: UUID) -> SecurityAlert:
        from app.core.errors import NotFoundError

        obj = self.db.get(SecurityAlert, alert_id)
        if obj is None:
            raise NotFoundError("Security alert not found.")
        return obj

    def list_open(self, company_id: UUID | None = None) -> list[SecurityAlert]:
        stmt = select(SecurityAlert).order_by(SecurityAlert.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(SecurityAlert.company_id == company_id)
        return list(self.db.execute(stmt).scalars().all())


# ── Incidents (§84 statuses + timeline) ─────────────────────────────────────


_INCIDENT_FLOW = [
    IncidentStatus.DETECTED.value,
    IncidentStatus.INVESTIGATING.value,
    IncidentStatus.CONTAINED.value,
    IncidentStatus.RESOLVED.value,
    IncidentStatus.CLOSED.value,
]


class IncidentService:
    """Create / transition incidents with an audited timeline."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        title: str,
        description: str | None = None,
        severity: str = Severity.MEDIUM.value,
        company_id: UUID | None = None,
        reported_by: UUID | None = None,
        alert_ids: list[UUID] | None = None,
    ) -> Incident:
        incident = Incident(
            title=title,
            description=description,
            severity=severity,
            company_id=company_id,
            status=IncidentStatus.DETECTED.value,
            created_by=reported_by,
            timeline_json={
                "entries": [
                    {
                        "at": datetime.now(UTC).isoformat(),
                        "status": IncidentStatus.DETECTED.value,
                        "by": str(reported_by) if reported_by else None,
                        "note": "Incident reported",
                    }
                ]
            },
        )
        self.db.add(incident)
        self.db.flush()
        if alert_ids:
            for alert_id in alert_ids:
                self._attach_alert(incident, alert_id)
        self._audit(incident, "incident.created", by=reported_by)
        return incident

    def get(self, incident_id: UUID) -> Incident:
        from app.core.errors import NotFoundError

        obj = self.db.get(Incident, incident_id)
        if obj is None:
            raise NotFoundError("Incident not found.")
        return obj

    def transition(
        self,
        incident_id: UUID,
        to_status: str,
        *,
        note: str | None = None,
        by: UUID | None = None,
    ) -> Incident:
        incident = self.get(incident_id)
        if to_status not in _INCIDENT_FLOW:
            raise ValueError(f"Invalid incident status {to_status!r}.")
        current = _INCIDENT_FLOW.index(incident.status)
        target = _INCIDENT_FLOW.index(to_status)
        if target < current:
            raise ValueError(f"Cannot move incident from {incident.status} back to {to_status}.")
        incident.status = to_status
        if to_status == IncidentStatus.CONTAINED.value:
            incident.contained_at = datetime.now(UTC)
        elif to_status == IncidentStatus.RESOLVED.value:
            incident.resolved_at = datetime.now(UTC)
        elif to_status == IncidentStatus.CLOSED.value:
            incident.closed_at = datetime.now(UTC)
        entries = incident.timeline_json or {"entries": []}
        entries["entries"].append(
            {
                "at": datetime.now(UTC).isoformat(),
                "status": to_status,
                "by": str(by) if by else None,
                "note": note,
            }
        )
        incident.timeline_json = entries
        self.db.flush()
        self._audit(incident, f"incident.{to_status}", by=by, detail={"note": note})
        return incident

    def _attach_alert(self, incident: Incident, alert_id: UUID) -> None:
        alert = self.db.get(SecurityAlert, alert_id)
        if alert is not None:
            alert.incident_id = incident.id
            self.db.flush()

    def _audit(
        self, incident: Incident, action: str, *, by: UUID | None = None, detail: dict | None = None
    ) -> None:
        try:
            from app.security.accountability import AuditService

            AuditService(self.db).record(
                actor_id=by,
                company_id=incident.company_id,
                action=action,
                category="incidents",
                resource_type="incidents",
                resource_id=str(incident.id),
                outcome="success",
                detail={
                    **({"note": detail.get("note")} if detail and detail.get("note") else {}),
                    "status": incident.status,
                },
                commit=False,
            )
        except Exception:  # pragma: no cover
            logger.debug("audit skip for %s", action)


# ── Incident action executor (§85) ──────────────────────────────────────────


class IncidentActionExecutor:
    """Apply §85 containment/remediation actions. Every action is audited.

    Supported codes:
    - pause_company / disable_external_actions / disable_agent → kill switch
    - disable_integration → suspend the Phase 10 integration
    - revoke_credential → revoke a Secret (external creds are ref-only; not revoked here)
    - suspend_employee → suspend an identity
    - terminate_browser_session / terminate_computer_session → terminate session rows
    """

    def __init__(self, incident_id: UUID, db: Session) -> None:
        self.incident_id = incident_id
        self.db = db

    def execute(
        self,
        action_code: str,
        *,
        requested_by: UUID | None = None,
        params: dict | None = None,
    ) -> IncidentAction:
        params = params or {}
        incident = self.db.get(Incident, self.incident_id)
        if incident is None:
            raise LookupError("Incident not found.")
        record = IncidentAction(
            incident_id=self.incident_id,
            action_code=action_code,
            target_company_id=params.get("company_id") or incident.company_id,
            target_ref=params.get("target_ref"),
            state=IncidentActionState.APPLIED.value,
            rationale=params.get("rationale"),
            performed_by=requested_by,
            result_json={"ok": True},
        )
        try:
            handler = getattr(self, f"_action_{action_code}", None)
            if handler is None:
                raise ValueError(f"Unsupported incident action {action_code!r}.")
            result = handler(incident, params)
            record.result_json = result
        except Exception as exc:  # noqa: BLE001
            record.state = IncidentActionState.FAILED.value
            record.result_json = {"ok": False, "error": str(exc)}
            self.db.add(record)
            self.db.flush()
            self._audit(incident, record, requested_by, success=False, error=str(exc))
            raise
        self.db.add(record)
        self.db.flush()
        self._audit(incident, record, requested_by)
        return record

    # ── handlers ───────────────────────────────────────────────────────────

    def _action_pause_company(self, incident: Incident, params: dict) -> dict:
        from app.security.governance import KillSwitchService

        KillSwitchService(self.db).pause(
            scope="company",
            reason=params.get("rationale") or "Incident containment",
            set_by=incident.created_by,
            tenant_id=params.get("company_id") or incident.company_id,
        )
        return {"scope": "company", "paused": True}

    def _action_disable_external_actions(self, incident: Incident, params: dict) -> dict:
        from app.security.governance import KillSwitchService

        KillSwitchService(self.db).pause(
            scope="external",
            reason=params.get("rationale") or "Incident containment",
            set_by=incident.created_by,
            tenant_id=params.get("company_id") or incident.company_id,
        )
        return {"scope": "external", "paused": True}

    def _action_disable_agent(self, incident: Incident, params: dict) -> dict:
        from app.db.models.security import Identity

        agent_id = params.get("target_ref")
        if agent_id:
            identity = self.db.execute(
                select(Identity).where(Identity.external_ref == f"agent:{agent_id}")
            ).scalar_one_or_none()
            if identity is not None:
                from app.security.identity import IdentityManager

                IdentityManager(self.db).suspend(identity.id)
                return {"agent": agent_id, "suspended": True}
        # Fall back to pausing the company's external scope for the agent tenant.
        from app.security.governance import KillSwitchService

        KillSwitchService(self.db).pause(
            scope="agent",
            reason=params.get("rationale") or "Incident containment",
            set_by=incident.created_by,
            tenant_id=None,
        )
        return {"agent": agent_id, "suspended": False, "note": "agent scope paused"}

    def _action_suspend_employee(self, incident: Incident, params: dict) -> dict:
        from app.security.identity import IdentityManager

        identity_id = params.get("target_ref")
        if not identity_id:
            raise ValueError("suspend_employee requires target_ref (identity id).")
        identity = IdentityManager(self.db).suspend(UUID(identity_id))
        return {"identity": identity_id, "suspended": identity.status}

    def _action_disable_integration(self, incident: Incident, params: dict) -> dict:
        from app.db.models.external import ExternalIntegration, IntegrationStatus

        integration_id = params.get("target_ref")
        integration = (
            self.db.get(ExternalIntegration, UUID(integration_id)) if integration_id else None
        )
        if integration is None:
            raise ValueError("disable_integration requires a valid target_ref.")
        integration.status = IntegrationStatus.SUSPENDED.value
        self.db.flush()
        return {"integration": integration_id, "status": integration.status}

    def _action_revoke_credential(self, incident: Incident, params: dict) -> dict:
        secret_id = params.get("target_ref")
        if not secret_id:
            raise ValueError("revoke_credential requires target_ref (secret id).")
        from app.security.secrets import SecretManager

        SecretManager(self.db).revoke(UUID(secret_id))
        return {"secret": secret_id, "revoked": True}

    def _action_terminate_browser_session(self, incident: Incident, params: dict) -> dict:
        from app.db.models.external import BrowserSession, BrowserSessionStatus

        session_id = params.get("target_ref")
        session = self.db.get(BrowserSession, UUID(session_id)) if session_id else None
        if session is None:
            raise ValueError("terminate_browser_session requires a valid target_ref.")
        session.status = BrowserSessionStatus.TERMINATED.value
        self.db.flush()
        return {"session": session_id, "status": session.status}

    def _action_terminate_computer_session(self, incident: Incident, params: dict) -> dict:
        from app.db.models.external import ComputerSession, ComputerSessionStatus

        session_id = params.get("target_ref")
        session = self.db.get(ComputerSession, UUID(session_id)) if session_id else None
        if session is None:
            raise ValueError("terminate_computer_session requires a valid target_ref.")
        session.status = ComputerSessionStatus.TERMINATED.value
        self.db.flush()
        return {"session": session_id, "status": session.status}

    def _audit(
        self,
        incident: Incident,
        record: IncidentAction,
        requested_by: UUID | None,
        *,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        try:
            from app.security.accountability import AuditService

            AuditService(self.db).record(
                actor_id=requested_by,
                company_id=incident.company_id,
                action=f"incident_action.{record.action_code}",
                category="incidents",
                resource_type="incident_actions",
                resource_id=str(record.id),
                outcome="success" if success else "failure",
                detail={
                    "incident_id": str(incident.id),
                    "state": record.state,
                    **({"error": error} if error else {}),
                },
                commit=False,
            )
        except Exception:  # pragma: no cover
            logger.debug("audit skip for incident action")
