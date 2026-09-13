"""Computer session manager — bounded simulated desktop use (Phase 10, §51).

Mirror of the browser session manager for the computer surface: a long-lived
session over the deterministic mock desktop, input actions with per-action
risk classification, an approval gate for the §67 purchase path, structured
(untrusted) screen observations, and full persistence + audit. Real desktop
automation (OS-level screen access) is an explicit Phase 11 hardening item.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.external import (
    ApprovalStatus,
    ComputerAction,
    ComputerActionType,
    ComputerObservation,
    ComputerSession,
    ComputerSessionStatus,
    ContentType,
    RiskLevel,
)
from app.external.computer.mock_driver import MockComputerDriver
from app.external.computer.policy import approval_status_for, classify_risk
from app.external.events import ExternalEventLogger, ExternalEvents
from app.external.types import ExternalValidationFailure
from app.startup.gates import ApprovalGateManager, ApprovalGateVerificationError


class ComputerSessionLimitError(ValueError):
    """A computer session/action limit was exceeded."""


class SensitiveComputerActionBlocked(ValueError):
    """A sensitive computer action (e.g. purchase) was refused pending approval."""


class ComputerSessionManager:
    """Manage simulated desktop sessions: lifecycle, inputs, observations."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = ExternalEventLogger(db)
        self._driver = MockComputerDriver()

    # ── Lifecycle ─────────────────────────────────────────────────────

    def create(
        self,
        *,
        company_id: UUID,
        employee_id: UUID | None = None,
        agent_id: UUID | None = None,
        **owner: Any,
    ) -> ComputerSession:
        # Governance gate: no session minting while external scope is paused.
        from app.db.models.security import SystemFlagScope
        from app.security.governance import GovernanceGuard

        GovernanceGuard(self._db).require(SystemFlagScope.EXTERNAL.value, tenant_id=company_id)
        active = self._db.scalar(
            sa_select(func.count())
            .select_from(ComputerSession)
            .where(
                ComputerSession.company_id == company_id,
                ComputerSession.status.in_(
                    [
                        ComputerSessionStatus.CREATED,
                        ComputerSessionStatus.ACTIVE,
                        ComputerSessionStatus.PAUSED,
                    ]
                ),
            )
        )
        if (active or 0) >= settings.max_computer_sessions:
            raise ComputerSessionLimitError("Company computer-session limit reached")
        session = ComputerSession(
            company_id=company_id,
            employee_id=employee_id,
            agent_id=agent_id,
            status=ComputerSessionStatus.CREATED,
            screen=json.dumps(self._driver.snapshot(), default=str),
            cursor=json.dumps(self._driver.cursor),
            policy=json.dumps({"simulated": True, "purchase_actions_require_approval": True}),
            action_count=0,
            started_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
        )
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        # Create initial observation
        self._observe(session)
        self._events.log(
            action=ExternalEvents.COMPUTER_SESSION_CREATED,
            company_id=company_id,
            actor="system",
            target_type="computer_session",
            target_id=session.id,
        )
        return session

    def get(self, company_id: UUID, session_id: UUID) -> ComputerSession:
        session = self._db.get(ComputerSession, session_id)
        if session is None or session.company_id != company_id:
            raise ExternalValidationFailure(f"Computer session {session_id} not found")
        return session

    def list_(self, company_id: UUID) -> list[ComputerSession]:
        return list(
            self._db.execute(
                sa_select(ComputerSession)
                .where(ComputerSession.company_id == company_id)
                .order_by(ComputerSession.created_at.desc())
            )
            .scalars()
            .all()
        )

    def pause(self, company_id: UUID, session_id: UUID) -> ComputerSession:
        session = self.get(company_id, session_id)
        if session.status in {
            ComputerSessionStatus.COMPLETED,
            ComputerSessionStatus.TERMINATED,
            ComputerSessionStatus.FAILED,
        }:
            raise ExternalValidationFailure(f"Cannot pause a {session.status.value} session")
        session.status = ComputerSessionStatus.PAUSED
        session.last_activity_at = datetime.now(UTC)
        self._db.commit()
        self._events.log(
            action=ExternalEvents.COMPUTER_SESSION_PAUSED,
            company_id=company_id,
            target_type="computer_session",
            target_id=session_id,
        )
        return session

    def terminate(self, company_id: UUID, session_id: UUID) -> ComputerSession:
        session = self.get(company_id, session_id)
        session.status = ComputerSessionStatus.TERMINATED
        session.terminated_at = datetime.now(UTC)
        session.last_activity_at = datetime.now(UTC)
        self._db.commit()
        self._events.log(
            action=ExternalEvents.COMPUTER_SESSION_TERMINATED,
            company_id=company_id,
            target_type="computer_session",
            target_id=session_id,
        )
        return session

    # ── Actions ───────────────────────────────────────────────────────

    def action(
        self,
        company_id: UUID,
        session_id: UUID,
        *,
        action_type: str,
        input_data: dict[str, Any] | None = None,
        approved_gate_id: UUID | None = None,
    ) -> ComputerAction:
        session = self._require_active(company_id, session_id)
        started = datetime.now(UTC)
        action = ComputerAction(
            session_id=session.id,
            company_id=company_id,
            action_type=ComputerActionType(action_type),
            input=json.dumps(input_data) if input_data else None,
            status="pending",
            risk_level=RiskLevel.LOW,
            approval_status=ApprovalStatus.NOT_REQUIRED,
        )
        self._db.add(action)
        self._db.commit()
        self._db.refresh(action)

        try:
            risk = classify_risk(action_type, self._driver, action_type, input_data or {})
            action.risk_level = risk
            action.approval_status = approval_status_for(risk)
            if risk is RiskLevel.HIGH and not approved_gate_id:
                action.status = "blocked_pending_approval"
                self._db.commit()
                raise SensitiveComputerActionBlocked(
                    f"Computer action {action_type} requires approval"
                )
            if risk is RiskLevel.HIGH and approved_gate_id:
                try:
                    ApprovalGateManager(self._db).verify_approved(
                        company_id,
                        approved_gate_id,
                        gate_type="external_action_approval",
                        action=f"computer.{action_type}",
                    )
                except ApprovalGateVerificationError as exc:
                    raise SensitiveComputerActionBlocked(str(exc)) from exc

            result = self._driver.perform(action_type, input_data or {})
            action.status = "succeeded"
            action.result = json.dumps(result, default=str)[: settings.max_external_payload_bytes]
            action.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            action.verification = json.dumps(
                {"content_type": ContentType.EXTERNAL_UNTRUSTED_CONTENT.value, "simulated": True}
            )
            session.action_count += 1
            obs = self._observe(session)
            session.last_activity_at = datetime.now(UTC)
            self._db.commit()
            self._events.log(
                action=ExternalEvents.COMPUTER_ACTION,
                company_id=company_id,
                target_type="computer_session",
                target_id=session_id,
                details={"action_type": action_type, "observation": obs.id.hex if obs else None},
            )
            return action
        except (
            ExternalValidationFailure,
            ComputerSessionLimitError,
            SensitiveComputerActionBlocked,
        ) as exc:
            if action.status != "blocked_pending_approval":
                action.status = "failed"
                action.error = str(exc)[: settings.max_external_payload_bytes]
            action.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            session.last_activity_at = datetime.now(UTC)
            self._db.commit()
            raise

    def observations(self, company_id: UUID, session_id: UUID) -> list[ComputerObservation]:
        session = self.get(company_id, session_id)
        return list(
            self._db.execute(
                sa_select(ComputerObservation)
                .where(ComputerObservation.session_id == session.id)
                .order_by(ComputerObservation.observation_number.asc())
            )
            .scalars()
            .all()
        )

    # ── Internals ─────────────────────────────────────────────────────

    def _require_active(self, company_id: UUID, session_id: UUID) -> ComputerSession:
        session = self.get(company_id, session_id)
        if session.status not in {
            ComputerSessionStatus.CREATED,
            ComputerSessionStatus.ACTIVE,
            ComputerSessionStatus.PAUSED,
        }:
            raise ExternalValidationFailure(
                f"Session is {session.status.value}; no further actions allowed"
            )
        if session.action_count >= settings.max_computer_actions:
            raise ComputerSessionLimitError("Computer session action budget exceeded")
        if self._expired(session):
            self.terminate(company_id, session_id)
            raise ComputerSessionLimitError("Computer session expired")
        return session

    def _observe(self, session: ComputerSession) -> ComputerObservation:
        obs = self._driver.observe()
        number = (
            self._db.scalars(
                sa_select(func.max(ComputerObservation.observation_number)).where(
                    ComputerObservation.session_id == session.id
                )
            ).one()
        ) or 0
        number += 1
        row = ComputerObservation(
            session_id=session.id,
            company_id=session.company_id,
            observation_number=number,
            snapshot=json.dumps(obs.snapshot, default=str)[: settings.max_page_size_bytes],
            screenshot_ref=obs.screenshot_ref,
            content_type=ContentType.EXTERNAL_UNTRUSTED_CONTENT,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def _expired(self, session: ComputerSession) -> bool:
        # SQLite returns naive datetimes; normalize to UTC-naive for comparison.
        now = datetime.now(UTC).replace(tzinfo=None)
        anchor = (
            _as_naive(session.started_at)
            if session.started_at
            else _as_naive(session.last_activity_at)
        )
        if anchor is None:
            return False
        return (now - anchor).total_seconds() / 60 >= settings.max_computer_session_duration_minutes


def _as_naive(value: datetime) -> datetime:
    """Return a UTC-naive datetime for portable comparisons (SQLite-safe)."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value
