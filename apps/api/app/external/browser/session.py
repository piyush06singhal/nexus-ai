"""Browser session manager — bounded simulated browsing (Phase 10, §50).

``BrowserSessionManager`` composes everything the plan requires: a long-lived
session that survives across bounded actions, the deterministic mock driver,
domain restriction, sensitive-action approval through the shared approval gate
system, and structured untrusted observations. Every session/action/observation
has a persisted row (``browser_sessions``/``browser_actions``/
``browser_observations``) and every lifecycle transition is audited via the
shared event logger. No real browser, no real network anywhere.
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
    BrowserAction,
    BrowserActionType,
    BrowserObservation,
    BrowserSession,
    BrowserSessionStatus,
    ContentType,
    RiskLevel,
)
from app.external.browser.interaction import click, resolve_target, scroll, select, type_text
from app.external.browser.mock_driver import FIXTURE_DOMAIN, MockBrowserDriver
from app.external.browser.navigation import go_back, go_forward, navigate_to, refresh
from app.external.browser.policy import approval_status_for, classify_risk
from app.external.events import ExternalEventLogger, ExternalEvents
from app.external.types import ExternalValidationFailure
from app.startup.gates import ApprovalGateManager, ApprovalGateVerificationError


class BrowserSessionLimitError(ValueError):
    """A session or company limit was exceeded (budget/domain/session)."""


class SensitiveBrowserActionBlocked(ValueError):
    """A sensitive browser action was refused pending approval."""


class BrowserSessionManager:
    """Manage one browser-use session: lifecycle, actions, observations."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = ExternalEventLogger(db)
        self._driver = MockBrowserDriver()

    # ── Lifecycle ─────────────────────────────────────────────────────

    def create(
        self,
        *,
        company_id: UUID,
        allowed_domains: list[str] | None = None,
        employee_id: UUID | None = None,
        agent_id: UUID | None = None,
        **owner: Any,
    ) -> BrowserSession:
        active = self._db.scalar(
            sa_select(func.count())
            .select_from(BrowserSession)
            .where(
                BrowserSession.company_id == company_id,
                BrowserSession.status.in_(
                    [
                        BrowserSessionStatus.CREATED,
                        BrowserSessionStatus.ACTIVE,
                        BrowserSessionStatus.PAUSED,
                    ]
                ),
            )
        )
        if (active or 0) >= settings.max_browser_sessions:
            raise BrowserSessionLimitError("Company browser-session limit reached")
        session = BrowserSession(
            company_id=company_id,
            employee_id=employee_id,
            agent_id=agent_id,
            status=BrowserSessionStatus.CREATED,
            allowed_domains=json.dumps(allowed_domains or [FIXTURE_DOMAIN]),
            policy=json.dumps(
                {"fixture_domain": FIXTURE_DOMAIN, "sensitive_actions_require_approval": True}
            ),
            action_count=0,
            navigation_count=0,
            started_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
        )
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        self._events.log(
            action=ExternalEvents.BROWSER_SESSION_CREATED,
            company_id=company_id,
            actor="system",
            target_type="browser_session",
            target_id=session.id,
        )
        return session

    def get(self, company_id: UUID, session_id: UUID) -> BrowserSession:
        session = self._db.get(BrowserSession, session_id)
        if session is None or session.company_id != company_id:
            raise ExternalValidationFailure(f"Browser session {session_id} not found")
        return session

    def list_(self, company_id: UUID) -> list[BrowserSession]:
        return list(
            self._db.execute(
                sa_select(BrowserSession)
                .where(BrowserSession.company_id == company_id)
                .order_by(BrowserSession.created_at.desc())
            )
            .scalars()
            .all()
        )

    def pause(self, company_id: UUID, session_id: UUID) -> BrowserSession:
        session = self.get(company_id, session_id)
        if session.status in {
            BrowserSessionStatus.COMPLETED,
            BrowserSessionStatus.TERMINATED,
            BrowserSessionStatus.FAILED,
        }:
            raise ExternalValidationFailure(f"Cannot pause a {session.status.value} session")
        session.status = BrowserSessionStatus.PAUSED
        session.last_activity_at = datetime.now(UTC)
        self._db.commit()
        self._events.log(
            action=ExternalEvents.BROWSER_SESSION_PAUSED,
            company_id=company_id,
            target_type="browser_session",
            target_id=session_id,
        )
        return session

    def terminate(self, company_id: UUID, session_id: UUID) -> BrowserSession:
        session = self.get(company_id, session_id)
        session.status = BrowserSessionStatus.TERMINATED
        session.terminated_at = datetime.now(UTC)
        session.last_activity_at = datetime.now(UTC)
        self._db.commit()
        self._events.log(
            action=ExternalEvents.BROWSER_SESSION_TERMINATED,
            company_id=company_id,
            target_type="browser_session",
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
        target: dict[str, Any] | None = None,
        input_data: dict[str, Any] | None = None,
        approved_gate_id: UUID | None = None,
    ) -> BrowserAction:
        session = self._require_active(company_id, session_id)
        started = datetime.now(UTC)
        action = BrowserAction(
            session_id=session.id,
            company_id=company_id,
            action_type=BrowserActionType(action_type),
            target=json.dumps(target) if target else None,
            input=json.dumps(input_data) if input_data else None,
            status="pending",
            risk_level=RiskLevel.LOW,
            approval_status=ApprovalStatus.NOT_REQUIRED,
        )
        self._db.add(action)
        self._db.commit()
        self._db.refresh(action)

        try:
            risk = classify_risk(action_type, target)
            action.risk_level = risk
            action.approval_status = approval_status_for(risk)
            if risk is RiskLevel.HIGH and not approved_gate_id:
                action.status = "blocked_pending_approval"
                self._db.commit()
                raise SensitiveBrowserActionBlocked(
                    f"Browser action {action_type} requires approval"
                )
            if risk is RiskLevel.HIGH and approved_gate_id:
                try:
                    ApprovalGateManager(self._db).verify_approved(
                        company_id,
                        approved_gate_id,
                        gate_type="external_action_approval",
                        action=f"browser.{action_type}",
                    )
                except ApprovalGateVerificationError as exc:
                    raise SensitiveBrowserActionBlocked(str(exc)) from exc

            result = self._dispatch(session, action_type, target, input_data)
            action.status = "succeeded"
            action.result = json.dumps(result, default=str)[: settings.max_external_payload_bytes]
            action.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            action.verification = json.dumps(
                {
                    "content_type": ContentType.EXTERNAL_UNTRUSTED_CONTENT.value,
                    "fixture_domain": FIXTURE_DOMAIN,
                }
            )
            session.action_count += 1
            obs = self._observe(session)
            session.last_activity_at = datetime.now(UTC)
            self._db.commit()
            self._events.log(
                action=ExternalEvents.BROWSER_ACTION,
                company_id=company_id,
                target_type="browser_session",
                target_id=session_id,
                details={"action_type": action_type, "observation": obs.id.hex if obs else None},
            )
            return action
        except (
            ExternalValidationFailure,
            BrowserSessionLimitError,
            SensitiveBrowserActionBlocked,
        ) as exc:
            if action.status != "blocked_pending_approval":
                action.status = "failed"
                action.error = str(exc)[: settings.max_external_payload_bytes]
            action.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            session.last_activity_at = datetime.now(UTC)
            self._db.commit()
            raise

    def observations(self, company_id: UUID, session_id: UUID) -> list[BrowserObservation]:
        session = self.get(company_id, session_id)
        return list(
            self._db.execute(
                sa_select(BrowserObservation)
                .where(BrowserObservation.session_id == session.id)
                .order_by(BrowserObservation.observation_number.asc())
            )
            .scalars()
            .all()
        )

    # ── Internals ─────────────────────────────────────────────────────

    def _require_active(self, company_id: UUID, session_id: UUID) -> BrowserSession:
        session = self.get(company_id, session_id)
        if session.status not in {
            BrowserSessionStatus.CREATED,
            BrowserSessionStatus.ACTIVE,
            BrowserSessionStatus.PAUSED,
        }:
            raise ExternalValidationFailure(
                f"Session is {session.status.value}; no further actions allowed"
            )
        if session.action_count >= settings.max_browser_actions:
            raise BrowserSessionLimitError("Browser session action budget exceeded")
        if self._expired(session):
            self.terminate(company_id, session_id)
            raise BrowserSessionLimitError("Browser session expired")
        allowlist = _load_json_array(session.allowed_domains)
        if session.domain and allowlist and session.domain not in allowlist:
            raise BrowserSessionLimitError(
                f"Domain {session.domain!r} not allowed for this session"
            )
        return session

    def _dispatch(
        self,
        session: BrowserSession,
        action_type: str,
        target: dict[str, Any] | None,
        input_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        driver = self._driver
        history = _load_json_array(session.metadata_json)
        url = str((target or {}).get("url") or (input_data or {}).get("url") or "")
        current = history[-1] if history else None

        if action_type in {"open_page", "navigate"}:
            target_url = url or (current and current.get("url")) or _default_url(session, history)
            self._count_navigation(session)
            page = navigate_to(
                target_url, resolve=driver.resolve, history=history, forward_stack=[]
            )
            result = {"url": page.get("url"), "title": page.get("title"), "navigated": True}
            return self._persist_page(session, history, page, result)
        if action_type == "back":
            page = go_back(history, [])
            result = {"url": page.get("url"), "title": page.get("title"), "from_history": True}
            return self._persist_page(session, history, page, result)
        if action_type == "forward":
            page = go_forward(history, [])
            result = {"url": page.get("url"), "title": page.get("title"), "from_history": True}
            return self._persist_page(session, history, page, result)
        if action_type == "refresh":
            page = refresh(history)
            result = {"url": page.get("url"), "refreshed": True}
            return self._persist_page(session, history, page, result)

        page = current or driver.resolve(url or _default_url(session, history))
        if action_type == "click":
            selector = str(
                (target or {}).get("selector") or (input_data or {}).get("selector") or ""
            )
            element = resolve_target(page, selector)
            result = click(page, element)
            dest = result.get("navigates_to")
            if dest:
                self._count_navigation(session)
                page = navigate_to(dest, resolve=driver.resolve, history=history, forward_stack=[])
                result = {**result, "navigated_page": page.get("url")}
        elif action_type == "type":
            selector = str(
                (target or {}).get("selector") or (input_data or {}).get("selector") or ""
            )
            element = resolve_target(page, selector)
            result = type_text(page, element, str((input_data or {}).get("text") or ""))
        elif action_type == "select":
            selector = str(
                (target or {}).get("selector") or (input_data or {}).get("selector") or ""
            )
            element = resolve_target(page, selector)
            result = select(page, element, str((input_data or {}).get("option") or ""))
        elif action_type == "scroll":
            result = scroll(
                page,
                str((input_data or {}).get("direction") or "down"),
                int((input_data or {}).get("amount") or 300),
            )
        elif action_type == "extract_text":
            result = {"url": page.get("url"), "text": page.get("visible_text", "")[:4096]}
        elif action_type == "extract_links":
            result = {"url": page.get("url"), "links": page.get("links", [])[:50]}
        elif action_type == "screenshot":
            result = {
                "screenshot_ref": f"browser-{session.id.hex[:8]}-{session.action_count + 1}",
                "placeholder": True,
            }
        elif action_type == "wait":
            result = {"waited": True}
        else:
            raise ExternalValidationFailure(f"Unsupported browser action {action_type!r}")

        return self._persist_page(session, history, page, result)

    def _persist_page(
        self,
        session: BrowserSession,
        history: list[Any],
        page: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        session.metadata_json = json.dumps(history, default=str)[
            : settings.max_external_payload_bytes
        ]
        session.current_url = page.get("url")
        session.domain = _host(page.get("url", ""))
        self._db.commit()
        return result

    def _observe(self, session: BrowserSession) -> BrowserObservation:
        driver = self._driver
        history = _load_json_array(session.metadata_json)
        page = (
            history[-1]
            if history
            else {
                "url": session.current_url or "",
                "title": "no page",
                "visible_text": "",
                "interactive": [],
                "links": [],
                "forms": [],
            }
        )
        obs = driver.observe(page)
        number = (
            self._db.scalars(
                sa_select(func.max(BrowserObservation.observation_number)).where(
                    BrowserObservation.session_id == session.id
                )
            ).one()
        ) or 0
        number += 1
        row = BrowserObservation(
            session_id=session.id,
            company_id=session.company_id,
            observation_number=number,
            url=obs.url,
            title=obs.title,
            snapshot=json.dumps(obs.snapshot, default=str)[: settings.max_page_size_bytes],
            screenshot_ref=obs.screenshot_ref,
            content_type=obs.content_type,
            page_state=json.dumps(obs.page_state, default=str)[: settings.max_page_size_bytes],
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def _count_navigation(self, session: BrowserSession) -> None:
        if session.navigation_count >= settings.max_browser_navigations:
            raise BrowserSessionLimitError("Browser navigation budget exceeded")
        session.navigation_count += 1

    def _navigation_budget(self, session: BrowserSession) -> bool:
        return session.navigation_count < settings.max_browser_navigations

    def _expired(self, session: BrowserSession) -> bool:
        # SQLite returns naive datetimes; normalize to UTC-naive for comparison.
        now = datetime.now(UTC).replace(tzinfo=None)
        anchor = (
            _as_naive(session.started_at)
            if session.started_at
            else _as_naive(session.last_activity_at)
        )
        if anchor is None:
            return False
        age_minutes = (now - anchor).total_seconds() / 60
        return age_minutes >= settings.max_browser_session_duration_minutes


def _as_naive(value: datetime) -> datetime:
    """Return a UTC-naive datetime for portable comparisons (SQLite-safe)."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _load_json_array(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else [value]
    except (ValueError, TypeError):
        return []


def _default_url(session: BrowserSession, history: list[dict[str, Any]]) -> str:
    if history:
        return str(history[-1].get("url", ""))
    return FIXTURE_DOMAIN and f"https://{FIXTURE_DOMAIN}/" or ""


def _host(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0] or ""
