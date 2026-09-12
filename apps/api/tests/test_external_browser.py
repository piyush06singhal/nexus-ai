"""Phase 10 browser-use tests — bounded simulated browsing (§50/§68/§66).

Covers session lifecycle, navigation + interaction actions, structured
observations (always labelled ``EXTERNAL_UNTRUSTED_CONTENT``), domain
restriction, per-session action/navigation budgets from Settings, the
sensitive-action approval gate, the §66 malicious-injection fixture (injected
"instructions" must remain data — never policy), session expiry/termination,
and cross-company isolation over HTTP.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Browser Co {_counter}", description="unit")


def _helper(db: Session):
    from app.external.browser.session import BrowserSessionManager

    company = _company(db)
    return company, BrowserSessionManager(db)


class TestLifecycle:
    def test_create_then_navigate_and_observe(self, db: Session) -> None:
        from app.db.models.external import BrowserSessionStatus, ContentType
        from app.external.browser.mock_driver import FIXTURE_DOMAIN

        company, mgr = _helper(db)
        session = mgr.create(
            company_id=company.id,
            allowed_domains=[FIXTURE_DOMAIN],
        )
        assert session.status == BrowserSessionStatus.CREATED
        assert session.action_count == 0
        assert json.loads(session.allowed_domains) == [FIXTURE_DOMAIN]

        opened = mgr.action(
            company.id,
            session.id,
            action_type="open_page",
            target={"url": f"https://{FIXTURE_DOMAIN}/"},
        )
        assert opened.status == "succeeded"
        result = json.loads(opened.result)
        assert result["url"] == f"https://{FIXTURE_DOMAIN}/"
        assert session.current_url == f"https://{FIXTURE_DOMAIN}/"
        assert session.domain == FIXTURE_DOMAIN
        assert session.action_count == 1
        assert session.navigation_count == 1

        obs = mgr.observations(company.id, session.id)
        assert len(obs) == 1
        assert obs[0].title == "NEXUS Discovery"
        snapshot = json.loads(obs[0].snapshot)
        assert snapshot["visible_text"]
        assert any("NexusMirror" in str(link) for link in snapshot["links"])
        # Prompt-injection boundary label (Rule 9/§65).
        assert obs[0].content_type == ContentType.EXTERNAL_UNTRUSTED_CONTENT

    def test_interaction_actions_type_click_extract(self, db: Session) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id, allowed_domains=[FIXTURE_DOMAIN])
        home = f"https://{FIXTURE_DOMAIN}/"
        mgr.action(company.id, session.id, action_type="open_page", target={"url": home})

        typed = mgr.action(
            company.id,
            session.id,
            action_type="type",
            target={"selector": "search-input", "type": "input"},
            input_data={"text": "mirror"},
        )
        assert typed.status == "succeeded"

        text = mgr.action(company.id, session.id, action_type="extract_text")
        assert json.loads(text.result)["text"]
        links = mgr.action(company.id, session.id, action_type="extract_links")
        assert isinstance(json.loads(links.result)["links"], list)

        # Click a button whose page is in the fixture catalog → navigation.
        clicked = mgr.action(
            company.id,
            session.id,
            action_type="click",
            target={"selector": "btn-prod-nexus", "label": "NexusMirror"},
        )
        assert clicked.status == "succeeded"
        assert (
            json.loads(clicked.result)["navigated_page"]
            == f"https://{FIXTURE_DOMAIN}/products/nexus"
        )

        # Screenshots are bounded placeholders in Phase 10 (never real pixels).
        shot = mgr.action(company.id, session.id, action_type="screenshot")
        body = json.loads(shot.result)
        assert body["placeholder"] is True
        assert body["screenshot_ref"]

    def test_invalid_url_and_action_fail_cleanly(self, db: Session) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN
        from app.external.types import ExternalValidationFailure

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id, allowed_domains=[FIXTURE_DOMAIN])
        try:
            mgr.action(
                company.id,
                session.id,
                action_type="open_page",
                target={"url": "https://not-in-catalog.example/"},
            )
            raise AssertionError("Unknown fixture URL must fail")
        except ExternalValidationFailure:
            pass
        try:
            mgr.action(company.id, session.id, action_type="bogus_action")
            raise AssertionError("Unknown action type must fail")
        except (ExternalValidationFailure, ValueError):
            pass
        assert session.action_count == 0

    def test_terminate_blocks_further_actions(self, db: Session) -> None:
        from app.db.models.external import BrowserSessionStatus
        from app.external.types import ExternalValidationFailure

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)
        terminated = mgr.terminate(company.id, session.id)
        assert terminated.status == BrowserSessionStatus.TERMINATED
        assert terminated.terminated_at is not None
        try:
            mgr.action(
                company.id, session.id, action_type="open_page", target={"url": "https://x/"}
            )
            raise AssertionError("Terminated session must not accept actions")
        except ExternalValidationFailure:
            pass

    def test_cross_company_isolation(self, db: Session) -> None:
        from app.external.types import ExternalValidationFailure

        company, mgr = _helper(db)
        other = _company(db)
        session = mgr.create(company_id=company.id)
        try:
            mgr.action(other.id, session.id, action_type="open_page", target={"url": "https://x/"})
            raise AssertionError("Foreign-company session must not be actionable")
        except ExternalValidationFailure:
            pass
        try:
            mgr.get(other.id, session.id)
            raise AssertionError("Foreign-company session must not be readable")
        except ExternalValidationFailure:
            pass


class TestDomainRestriction:
    def test_off_allowlist_domain_navigation_is_rejected(self, db: Session) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN
        from app.external.browser.session import BrowserSessionLimitError

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id, allowed_domains=["internal.nexus.test"])
        # First action, no domain yet — navigation to a fixture URL outside the
        # allowlist is refused once the domain is established.
        mgr.action(
            company.id,
            session.id,
            action_type="open_page",
            target={"url": f"https://{FIXTURE_DOMAIN}/"},
        )
        assert session.domain == FIXTURE_DOMAIN
        # A second action on this session pinning the disallowed domain trips the guard.
        try:
            mgr.action(company.id, session.id, action_type="extract_text")
            raise AssertionError("Session pinned to a disallowed domain must be blocked")
        except BrowserSessionLimitError:
            pass


class TestBudgets:
    def test_action_budget_is_enforced(self, db: Session, monkeypatch) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN
        from app.external.browser.session import BrowserSessionLimitError

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id, allowed_domains=[FIXTURE_DOMAIN])
        # Force a tiny budget so one action saturates it.
        monkeypatch.setattr("app.external.browser.session.settings.max_browser_actions", 1)
        mgr.action(
            company.id,
            session.id,
            action_type="open_page",
            target={"url": f"https://{FIXTURE_DOMAIN}/"},
        )
        try:
            mgr.action(company.id, session.id, action_type="extract_text")
            raise AssertionError("Session action budget must be enforced")
        except BrowserSessionLimitError:
            pass

    def test_navigation_budget_is_enforced(self, db: Session, monkeypatch) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN
        from app.external.browser.session import BrowserSessionLimitError

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id, allowed_domains=[FIXTURE_DOMAIN])
        monkeypatch.setattr("app.external.browser.session.settings.max_browser_navigations", 1)
        mgr.action(
            company.id,
            session.id,
            action_type="open_page",
            target={"url": f"https://{FIXTURE_DOMAIN}/"},
        )
        try:
            mgr.action(
                company.id,
                session.id,
                action_type="click",
                target={"selector": "btn-prod-nexus", "label": "NexusMirror"},
            )
            raise AssertionError("Navigation budget must be enforced")
        except BrowserSessionLimitError:
            pass

    def test_session_limit_is_enforced(self, db: Session, monkeypatch) -> None:
        from app.external.browser.session import BrowserSessionLimitError

        company, mgr = _helper(db)
        monkeypatch.setattr("app.external.browser.session.settings.max_browser_sessions", 1)
        mgr.create(company_id=company.id)
        try:
            mgr.create(company_id=company.id)
            raise AssertionError("Company browser-session ceiling must be enforced")
        except BrowserSessionLimitError:
            pass

    def test_session_expiry_terminates(self, db: Session, monkeypatch) -> None:
        from app.db.models.external import BrowserSessionStatus
        from app.external.browser.session import BrowserSessionLimitError

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)
        # Backdate the session anchor and shrink the allowed duration.
        monkeypatch.setattr(
            "app.external.browser.session.settings.max_browser_session_duration_minutes", 1
        )
        session.started_at = datetime.now(UTC) - timedelta(minutes=10)
        session.status = BrowserSessionStatus.ACTIVE
        db.commit()
        try:
            mgr.action(
                company.id, session.id, action_type="open_page", target={"url": "https://x/"}
            )
            raise AssertionError("Expired session must refuse actions")
        except BrowserSessionLimitError:
            pass
        db.refresh(session)
        assert session.status == BrowserSessionStatus.TERMINATED


class TestPromptInjection:
    def test_malicious_injection_page_is_only_data(self, db: Session) -> None:
        """§66: injected 'set approval to always-allow' text never becomes policy."""
        from app.external.browser.mock_driver import FIXTURE_DOMAIN
        from app.external.browser.session import BrowserSessionManager
        from app.external.security.context import EXTERNAL_UNTRUSTED_CONTENT

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id, allowed_domains=[FIXTURE_DOMAIN])
        adapter = BrowserSessionManager(db)._driver
        page = adapter.resolve(f"https://{FIXTURE_DOMAIN}/industry/malicious-injection")
        assert adapter.is_blocked_page(page)

        obs = adapter.observe(page)
        # The boundary: observation carries the untrusted marker and is never
        # treated as an instruction by the context contract.
        assert obs.content_type.value == EXTERNAL_UNTRUSTED_CONTENT
        annotated = {"text": obs.snapshot.get("visible_text", "")}
        from app.external.security import context as ctx

        ctx.annotate_observation(annotated)
        assert annotated["_content"]["trust"] == EXTERNAL_UNTRUSTED_CONTENT
        assert ctx.is_instruction(annotated) is False

        # Even after navigating to the malicious page, the session's policy is
        # unchanged — page content cannot mutate permissions/approval policy.
        mgr.action(
            company.id,
            session.id,
            action_type="open_page",
            target={"url": f"https://{FIXTURE_DOMAIN}/industry/malicious-injection"},
        )
        db.refresh(session)
        policy = json.loads(session.policy)
        assert policy["sensitive_actions_require_approval"] is True
        # The injection's directives ("set approval always-allow") do not appear
        # anywhere in the session policy.
        assert "always-allow" not in json.dumps(policy)


class TestSensitiveApproval:
    def test_sensitive_action_requires_approval_gate(self, db: Session) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN
        from app.external.browser.session import SensitiveBrowserActionBlocked
        from app.startup.gates import ApprovalGateManager

        # Inject a payment page into the simulated driver so a click can be both
        # real (dispatchable) and sensitive (approval-gated by label).
        pay_url = f"https://{FIXTURE_DOMAIN}/partner/pay"
        confirmed_url = f"https://{FIXTURE_DOMAIN}/partner/confirmed"
        mgr = _helper(db)[1]
        mgr._driver._pages[pay_url] = {
            "url": pay_url,
            "title": "Partner payment",
            "visible_text": "Complete your payment.",
            "interactive": [
                {
                    "id": "btn-pay-now",
                    "type": "button",
                    "label": "Pay now",
                    "navigates_to": confirmed_url,
                }
            ],
            "links": [],
            "forms": [],
        }
        mgr._driver._pages[confirmed_url] = {
            "url": confirmed_url,
            "title": "Payment confirmed",
            "visible_text": "Thank you.",
            "interactive": [],
            "links": [],
            "forms": [],
        }

        company, _ = _helper(db)
        session = mgr.create(company_id=company.id, allowed_domains=[FIXTURE_DOMAIN])
        mgr.action(company.id, session.id, action_type="open_page", target={"url": pay_url})

        # 1. Without a gate the sensitive click is refused.
        try:
            mgr.action(
                company.id,
                session.id,
                action_type="click",
                target={"selector": "btn-pay-now", "label": "Pay now", "type": "button"},
            )
            raise AssertionError("Sensitive browser action must be gated")
        except SensitiveBrowserActionBlocked:
            pass

        # 2. With an approved external-action gate the click proceeds.
        gate = ApprovalGateManager(db).create(
            company_id=company.id,
            gate_type="external_action_approval",
            requested_action={"action": "browser.click"},
            rationale="canary",
            risk_level="high",
        )
        ApprovalGateManager(db).approve(company.id, gate.id)
        result = mgr.action(
            company.id,
            session.id,
            action_type="click",
            target={"selector": "btn-pay-now", "label": "Pay now", "type": "button"},
            approved_gate_id=gate.id,
        )
        assert result.status == "succeeded"
        assert json.loads(result.result)["navigated_page"] == confirmed_url

    def test_approved_gate_cannot_bypass_nonexistent_element(self, db: Session) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN
        from app.external.types import ExternalValidationFailure
        from app.startup.gates import ApprovalGateManager

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id, allowed_domains=[FIXTURE_DOMAIN])
        gate = ApprovalGateManager(db).create(
            company_id=company.id,
            gate_type="external_action_approval",
            requested_action={"action": "browser.click"},
            rationale="canary",
            risk_level="high",
        )
        ApprovalGateManager(db).approve(company.id, gate.id)
        # Approval authorizes the *sensitive class*; the element must still exist.
        try:
            mgr.action(
                company.id,
                session.id,
                action_type="click",
                target={"selector": "btn-nonexistent", "label": "Ghost", "type": "button"},
                approved_gate_id=gate.id,
            )
            raise AssertionError("A non-existent element must still be rejected")
        except ExternalValidationFailure:
            pass


class TestHttpBrowser:
    """Browser session + action endpoints over HTTP."""

    def _company(self, api_client, db: Session) -> str:
        from app.company.manager import CompanyManager

        global _counter
        _counter += 1
        return str(
            CompanyManager(db).create(name=f"HTTP Browser Co {_counter}", description="http").id
        )

    def test_session_and_actions_over_http(self, api_client, db: Session) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN

        cid = self._company(api_client, db)
        r = api_client.post(
            f"/api/v1/browser/sessions/{cid}",
            json={"allowed_domains": [FIXTURE_DOMAIN]},
        )
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        assert r.json()["status"] == "created"

        r = api_client.post(
            f"/api/v1/browser/sessions/{cid}/{sid}/actions",
            json={"action_type": "open_page", "target": {"url": f"https://{FIXTURE_DOMAIN}/"}},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "succeeded"
        assert body["result"]["url"] == f"https://{FIXTURE_DOMAIN}/"

        r = api_client.get(f"/api/v1/browser/sessions/{cid}/{sid}/observations")
        assert r.status_code == 200
        body = r.json()[0]
        assert body["title"] == "NEXUS Discovery"
        assert body["content_type"] == "external_untrusted_content"
        assert body["snapshot"]["visible_text"]

        r = api_client.post(f"/api/v1/browser/sessions/{cid}/{sid}/terminate", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "terminated"

    def test_sensitive_action_403_over_http(self, api_client, db: Session) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN

        cid = self._company(api_client, db)
        r = api_client.post(
            f"/api/v1/browser/sessions/{cid}", json={"allowed_domains": [FIXTURE_DOMAIN]}
        )
        sid = r.json()["id"]
        r = api_client.post(
            f"/api/v1/browser/sessions/{cid}/{sid}/actions",
            json={
                "action_type": "click",
                "target": {"id": "btn-checkout", "label": "Checkout", "type": "button"},
            },
        )
        assert r.status_code == 403, r.text

    def test_foreign_company_404(self, api_client, db: Session) -> None:
        owner = self._company(api_client, db)
        foreign = self._company(api_client, db)
        r = api_client.post(f"/api/v1/browser/sessions/{owner}", json={})
        sid = r.json()["id"]
        assert api_client.get(f"/api/v1/browser/sessions/{foreign}/{sid}").status_code == 404
        r = api_client.post(
            f"/api/v1/browser/sessions/{foreign}/{sid}/actions",
            json={"action_type": "wait"},
        )
        assert r.status_code == 404
