"""Phase 10 computer-use tests — bounded simulated desktop sessions (§51/§67).

Covers session lifecycle, screen observation, input actions (click/type/keyboard),
per-action risk classification, the §67 purchase-path approval gate, session
expiry/termination, and cross-company isolation over HTTP.
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
    return CompanyManager(db).create(name=f"Computer Co {_counter}", description="unit")


def _helper(db: Session):
    from app.external.computer.session import ComputerSessionManager

    company = _company(db)
    return company, ComputerSessionManager(db)


class TestLifecycle:
    def test_create_then_action_and_observe(self, db: Session) -> None:
        from app.db.models.external import ComputerSessionStatus, ContentType

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)
        assert session.status == ComputerSessionStatus.CREATED
        assert session.action_count == 0
        assert json.loads(session.policy)["purchase_actions_require_approval"] is True

        # First observation is created on session creation
        obs = mgr.observations(company.id, session.id)
        assert len(obs) >= 1
        assert obs[0].content_type.value == ContentType.EXTERNAL_UNTRUSTED_CONTENT.value
        snapshot = json.loads(obs[0].snapshot)
        assert snapshot["screen"] is not None
        assert snapshot["cursor"] is not None

    def test_input_actions_move_click_type(self, db: Session) -> None:
        from app.db.models.external import RiskLevel

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)

        moved = mgr.action(
            company.id,
            session.id,
            action_type="move_mouse",
            input_data={"x": 100, "y": 200},
        )
        assert moved.status == "succeeded"
        assert moved.risk_level == RiskLevel.LOW
        result = json.loads(moved.result)
        assert result["cursor"]["x"] == 100
        assert result["cursor"]["y"] == 200

        clicked = mgr.action(
            company.id,
            session.id,
            action_type="click",
            input_data={"element": "btn-reports"},
        )
        assert clicked.status == "succeeded"
        assert clicked.risk_level == RiskLevel.MEDIUM

        typed = mgr.action(
            company.id,
            session.id,
            action_type="type",
            input_data={"element": "fld-to", "text": "hello"},
        )
        assert typed.status == "succeeded"
        assert typed.risk_level == RiskLevel.MEDIUM

    def test_invalid_action_fails_cleanly(self, db: Session) -> None:
        from app.external.types import ExternalValidationFailure

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)
        try:
            mgr.action(company.id, session.id, action_type="bogus_action")
            raise AssertionError("Unknown action type must fail")
        except (ExternalValidationFailure, ValueError):
            pass
        assert session.action_count == 0

    def test_terminate_blocks_further_actions(self, db: Session) -> None:
        from app.db.models.external import ComputerSessionStatus
        from app.external.types import ExternalValidationFailure

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)
        terminated = mgr.terminate(company.id, session.id)
        assert terminated.status == ComputerSessionStatus.TERMINATED
        assert terminated.terminated_at is not None
        try:
            mgr.action(
                company.id, session.id, action_type="move_mouse", input_data={"x": 0, "y": 0}
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
            mgr.action(other.id, session.id, action_type="move_mouse", input_data={"x": 0, "y": 0})
            raise AssertionError("Foreign-company session must not be actionable")
        except ExternalValidationFailure:
            pass
        try:
            mgr.get(other.id, session.id)
            raise AssertionError("Foreign-company session must not be readable")
        except ExternalValidationFailure:
            pass


class TestBudgets:
    def test_action_budget_is_enforced(self, db: Session, monkeypatch) -> None:
        from app.external.computer.session import ComputerSessionLimitError

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)
        monkeypatch.setattr("app.external.computer.session.settings.max_computer_actions", 1)
        mgr.action(company.id, session.id, action_type="move_mouse", input_data={"x": 0, "y": 0})
        try:
            mgr.action(company.id, session.id, action_type="click", input_data={"x": 0, "y": 0})
            raise AssertionError("Session action budget must be enforced")
        except ComputerSessionLimitError:
            pass

    def test_session_limit_is_enforced(self, db: Session, monkeypatch) -> None:
        from app.external.computer.session import ComputerSessionLimitError

        company, mgr = _helper(db)
        monkeypatch.setattr("app.external.computer.session.settings.max_computer_sessions", 1)
        mgr.create(company_id=company.id)
        try:
            mgr.create(company_id=company.id)
            raise AssertionError("Company computer-session ceiling must be enforced")
        except ComputerSessionLimitError:
            pass

    def test_session_expiry_terminates(self, db: Session, monkeypatch) -> None:
        from app.db.models.external import ComputerSessionStatus
        from app.external.computer.session import ComputerSessionLimitError

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)
        monkeypatch.setattr(
            "app.external.computer.session.settings.max_computer_session_duration_minutes", 1
        )
        session.started_at = datetime.now(UTC) - timedelta(minutes=10)
        session.status = ComputerSessionStatus.ACTIVE
        db.commit()
        try:
            mgr.action(
                company.id, session.id, action_type="move_mouse", input_data={"x": 0, "y": 0}
            )
            raise AssertionError("Expired session must refuse actions")
        except ComputerSessionLimitError:
            pass
        db.refresh(session)
        assert session.status == ComputerSessionStatus.TERMINATED


class TestPurchaseApproval:
    def test_purchase_action_requires_approval_gate(self, db: Session) -> None:
        from app.external.computer.session import SensitiveComputerActionBlocked
        from app.startup.gates import ApprovalGateManager

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)

        # First navigate to checkout window by clicking the purchase button
        mgr.action(
            company.id,
            session.id,
            action_type="click",
            input_data={"element": "btn-purchase"},
        )

        # 1. Without a gate the purchase action is refused.
        try:
            mgr.action(
                company.id,
                session.id,
                action_type="click",
                input_data={"element": "btn-confirm"},
            )
            raise AssertionError("Purchase action must be gated")
        except SensitiveComputerActionBlocked:
            pass

        # 2. With an approved external-action gate the purchase proceeds.
        gate = ApprovalGateManager(db).create(
            company_id=company.id,
            gate_type="external_action_approval",
            requested_action={"action": "computer.click"},
            rationale="canary purchase",
            risk_level="high",
        )
        ApprovalGateManager(db).approve(company.id, gate.id)
        result = mgr.action(
            company.id,
            session.id,
            action_type="click",
            input_data={"element": "btn-confirm"},
            approved_gate_id=gate.id,
        )
        assert result.status == "succeeded"
        assert result.risk_level.value == "high"

    def test_approved_gate_cannot_bypass_invalid_purchase(self, db: Session) -> None:
        from app.external.types import ExternalValidationFailure
        from app.startup.gates import ApprovalGateManager

        company, mgr = _helper(db)
        session = mgr.create(company_id=company.id)
        gate = ApprovalGateManager(db).create(
            company_id=company.id,
            gate_type="external_action_approval",
            requested_action={"action": "computer.click"},
            rationale="canary",
            risk_level="high",
        )
        ApprovalGateManager(db).approve(company.id, gate.id)
        # Approval authorizes the *sensitive class*; invalid input must still be rejected.
        try:
            mgr.action(
                company.id,
                session.id,
                action_type="click",
                input_data={"x": -100, "y": -100, "button": "left", "element": "ghost"},
                approved_gate_id=gate.id,
            )
            raise AssertionError("Invalid purchase input must still reach the adapter")
        except ExternalValidationFailure:
            pass


class TestHttpComputer:
    """Computer session + action endpoints over HTTP."""

    def _company(self, api_client, db: Session) -> str:
        from app.company.manager import CompanyManager

        global _counter
        _counter += 1
        return str(
            CompanyManager(db).create(name=f"HTTP Computer Co {_counter}", description="http").id
        )

    def test_session_and_actions_over_http(self, api_client, db: Session) -> None:
        cid = self._company(api_client, db)
        r = api_client.post(f"/api/v1/computer/sessions/{cid}", json={})
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        assert r.json()["status"] == "created"

        r = api_client.post(
            f"/api/v1/computer/sessions/{cid}/{sid}/actions",
            json={"action_type": "move_mouse", "input": {"x": 50, "y": 60}},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "succeeded"
        # Cursor position is clamped to bounds
        assert body["result"]["cursor"]["x"] == 50
        assert body["result"]["cursor"]["y"] == 60

        r = api_client.post(
            f"/api/v1/computer/sessions/{cid}/{sid}/actions",
            json={"action_type": "click", "input": {"element": "btn-reports"}},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "succeeded"

        r = api_client.get(f"/api/v1/computer/sessions/{cid}/{sid}/observations")
        assert r.status_code == 200
        assert len(r.json()) >= 1
        assert r.json()[0]["content_type"] == "external_untrusted_content"

        r = api_client.post(f"/api/v1/computer/sessions/{cid}/{sid}/terminate", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "terminated"

    def test_purchase_action_403_over_http(self, api_client, db: Session) -> None:
        cid = self._company(api_client, db)
        r = api_client.post(f"/api/v1/computer/sessions/{cid}", json={})
        sid = r.json()["id"]
        # First navigate to checkout window
        r = api_client.post(
            f"/api/v1/computer/sessions/{cid}/{sid}/actions",
            json={"action_type": "click", "input": {"element": "btn-purchase"}},
        )
        assert r.status_code == 201, r.text
        # Then attempt purchase
        r = api_client.post(
            f"/api/v1/computer/sessions/{cid}/{sid}/actions",
            json={"action_type": "click", "input": {"element": "btn-confirm"}},
        )
        assert r.status_code == 403, r.text

    def test_foreign_company_404(self, api_client, db: Session) -> None:
        owner = self._company(api_client, db)
        foreign = self._company(api_client, db)
        r = api_client.post(f"/api/v1/computer/sessions/{owner}", json={})
        sid = r.json()["id"]
        assert api_client.get(f"/api/v1/computer/sessions/{foreign}/{sid}").status_code == 404
        r = api_client.post(
            f"/api/v1/computer/sessions/{foreign}/{sid}/actions",
            json={"action_type": "wait"},
        )
        assert r.status_code == 404
