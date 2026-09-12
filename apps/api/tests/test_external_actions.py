"""Phase 10 external-actions funnel tests — the governed path for one capability call.

``ExternalActionManager.create`` is the single choke point every external action
passes through (risk → policy → autonomy → approval → execute → scrub → verify →
recover → journal → audit). These tests pin the contract that matters for the
"email approval" flow (§70): an approval-required capability parks as
``awaiting_approval`` with an ``EXTERNAL_ACTION_APPROVAL`` gate, the operator
approves, and replay with the gate id executes the action **exactly once** (Rule
12: one approved gate authorizes exactly one action once). Also covered here: the
fresh-company default (unlisted ``external_action`` ⇒ require approval at every
level), the allow-matrix override that auto-runs low-risk reads, idempotency,
policy denial, cancellation, cross-company isolation over HTTP, and gate
single-use.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Action Co {_counter}", description="unit")


def _email_setup(db: Session, company_id: UUID):
    """Create an email integration with a connected, one-shot-secreted connection."""
    from app.external.integration import IntegrationService

    svc = IntegrationService(db)
    integration = svc.create(company_id=company_id, provider="email", name="Email")
    connection = svc.connect(
        company_id=company_id,
        integration_id=integration.id,
        auth_method="api_key",
        secret_value="mail-secret-9876543210",
        env_var_hint="INTEGRATION_EMAIL_API_KEY",
        scopes=["email:send"],
        permissions=["email:send"],
    )
    return integration, connection


def _approve_gate(db: Session, company_id: UUID, gate_id: UUID) -> None:
    from app.startup.gates import ApprovalGateManager

    ApprovalGateManager(db).approve(company_id, gate_id)


def _reset_mailbox() -> None:
    """Reset the module-global mock mailbox so counts are per-test deterministic."""
    from app.external.providers import email as email_module

    email_module._MAILBOX.pop("email", None)
    email_module._SENT.pop("email", None)
    email_module._DRAFTS.pop("email", None)
    email_module._seed_mailbox("email")


def _sent_count() -> int:
    from app.external.providers import email as email_module

    return len(email_module._SENT.get("email", []))


def _result(action) -> dict:
    return json.loads(action.result)


class TestApprovedGateExecutes:
    """The core contract: an approved gate must actually run the action."""

    def test_send_message_gates_then_executes_exactly_once(self, db: Session) -> None:
        from app.db.models.external import ExternalActionStatus
        from app.external.action import ExternalActionManager
        from app.external.result import ExternalActionError

        _reset_mailbox()
        company = _company(db)
        integration, connection = _email_setup(db, company.id)
        mgr = ExternalActionManager(db)
        payload = {
            "to": ["vendor@example.com"],
            "subject": "RFP follow-up",
            "body": "Per our call, send the signed SOW.",
        }

        # 1. High-risk, irreversible, approval-required capability parks.
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload=payload,
            action_type="send_message",
            connection_id=connection.id,
            idempotency_key="rfp-sow-1",
        )
        assert action.status == ExternalActionStatus.AWAITING_APPROVAL
        assert action.approval_status.value == "pending"
        assert action.approval_gate_id is not None

        # 2. The parked action must not have run the side effect yet.
        assert _sent_count() == 0

        # 3. Human approves the gate.
        _approve_gate(db, company.id, action.approval_gate_id)

        # 4. Replay with the approved gate executes and passes verification.
        executed = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload=payload,
            action_type="send_message",
            connection_id=connection.id,
            idempotency_key="rfp-sow-1",
            approved_gate_id=action.approval_gate_id,
        )
        assert executed.status == ExternalActionStatus.SUCCEEDED
        assert executed.approval_status.value == "approved"
        assert executed.approval_gate_id == action.approval_gate_id
        assert _result(executed)["message"]["status"] == "sent"
        assert executed.verification is not None

        # The side effect actually happened, exactly once.
        assert _sent_count() == 1

        # 5. The gate is consumed — no second action may reuse it (Rule 12).
        try:
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="send_message",
                payload=payload,
                action_type="send_message",
                connection_id=connection.id,
                idempotency_key="rfp-sow-2",
                approved_gate_id=action.approval_gate_id,
            )
            raise AssertionError("A consumed gate must not authorize a second action")
        except ExternalActionError as exc:
            assert exc.code == "gate_used"

        # 6. Journal is immutable: all three actions are recorded, the reused
        #    gate attempt is blocked and carries the refusal reason.
        journal = mgr.list_(company.id)
        statuses = sorted(a.status.value for a in journal)
        assert statuses == sorted(["blocked", "succeeded", "awaiting_approval"])
        blocked = next(a for a in journal if a.status.value == "blocked")
        assert "gate_used" in (blocked.error or "")

    def test_gate_reuse_after_success_is_blocked(self, db: Session) -> None:
        from app.db.models.external import ExternalActionStatus
        from app.external.action import ExternalActionManager
        from app.external.result import ExternalActionError

        _reset_mailbox()
        company = _company(db)
        integration, connection = _email_setup(db, company.id)
        mgr = ExternalActionManager(db)

        parked = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={"to": ["a@example.com"], "subject": "S", "body": "B"},
            connection_id=connection.id,
        )
        gate_id = parked.approval_gate_id
        _approve_gate(db, company.id, gate_id)

        executed = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={"to": ["a@example.com"], "subject": "S", "body": "B"},
            connection_id=connection.id,
            approved_gate_id=gate_id,
        )
        assert executed.status == ExternalActionStatus.SUCCEEDED

        # A *different* action with the same gate is refused.
        try:
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="send_message",
                payload={"to": ["b@example.com"], "subject": "S2", "body": "B2"},
                connection_id=connection.id,
                approved_gate_id=gate_id,
            )
            raise AssertionError("Reusing an approved gate for a second action is a violation")
        except ExternalActionError as exc:
            assert exc.code == "gate_used"


class TestAutonomyDefaults:
    def test_fresh_company_low_risk_read_requires_approval(self, db: Session) -> None:
        """Unlisted ``external_action`` ⇒ require approval at every level."""
        from app.db.models.external import ExternalActionStatus
        from app.external.action import ExternalActionManager

        company = _company(db)
        integration, connection = _email_setup(db, company.id)
        action = ExternalActionManager(db).create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "campaign"},
            connection_id=connection.id,
        )
        assert action.status == ExternalActionStatus.AWAITING_APPROVAL

    def test_allow_matrix_auto_runs_low_risk_read(self, db: Session) -> None:
        from app.db.models.external import ExternalActionStatus
        from app.external.action import ExternalActionManager
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)
        action = ExternalActionManager(db).create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "campaign"},
            connection_id=connection.id,
        )
        assert action.status == ExternalActionStatus.SUCCEEDED
        results = _result(action)
        assert any(m["id"] == "msg-001" for m in results["messages"])

    def test_high_risk_stays_gated_even_with_allow_matrix(self, db: Session) -> None:
        """Auto-allow covers low-risk reads only — HIGH/CRITICAL stay gated."""
        from app.db.models.external import ExternalActionStatus
        from app.external.action import ExternalActionManager
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)
        action = ExternalActionManager(db).create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={"to": ["x@example.com"], "subject": "S", "body": "B"},
            connection_id=connection.id,
        )
        assert action.status == ExternalActionStatus.AWAITING_APPROVAL


class TestIdempotency:
    def test_duplicate_succeeded_is_refused(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.result import ExternalActionError
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)
        mgr = ExternalActionManager(db)
        payload = {"to": ["p@example.com"], "subject": "S", "body": "B"}

        parked = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload=payload,
            action_type="send_message",
            connection_id=connection.id,
            idempotency_key="ship-email-42",
        )
        assert parked.status.value == "awaiting_approval"
        _approve_gate(db, company.id, parked.approval_gate_id)
        sent = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload=payload,
            action_type="send_message",
            connection_id=connection.id,
            idempotency_key="ship-email-42",
            approved_gate_id=parked.approval_gate_id,
        )
        assert sent.status.value == "succeeded"
        assert _sent_count() == 1

        # Replaying the same key is a duplicate — refused, no second send.
        try:
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="send_message",
                payload=payload,
                action_type="send_message",
                connection_id=connection.id,
                idempotency_key="ship-email-42",
                approved_gate_id=parked.approval_gate_id,
            )
            raise AssertionError("Duplicate idempotency key must be refused")
        except ExternalActionError as exc:
            assert exc.code == "duplicate"
        assert _sent_count() == 1


class TestPolicyDenial:
    def test_denied_capability_is_blocked(self, db: Session) -> None:
        from app.db.models.external import IntegrationPolicy, ScopeType
        from app.external.action import ExternalActionManager
        from app.external.result import ExternalActionError

        company = _company(db)
        integration, connection = _email_setup(db, company.id)
        db.add(
            IntegrationPolicy(
                company_id=company.id,
                integration_id=integration.id,
                scope_type=ScopeType.COMPANY,
                capability_pattern="send_message",
                allowed=False,
                require_approval=True,
                enabled=True,
            )
        )
        db.commit()

        mgr = ExternalActionManager(db)
        try:
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="send_message",
                payload={"to": ["x@example.com"], "subject": "S", "body": "B"},
                connection_id=connection.id,
            )
            raise AssertionError("A policy-denied capability must be blocked")
        except ExternalActionError as exc:
            assert exc.status == "blocked"
            assert exc.code == "policy_denied"

    def test_policy_override_downgrades_medium_capability_to_allowed(self, db: Session) -> None:
        """A MEDIUM capability overridden to LOW + require_approval=False auto-runs."""
        from app.db.models.external import (
            ExternalActionStatus,
            IntegrationPolicy,
            RiskLevel,
            ScopeType,
        )
        from app.external.action import ExternalActionManager
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)
        db.add(
            IntegrationPolicy(
                company_id=company.id,
                integration_id=integration.id,
                scope_type=ScopeType.COMPANY,
                capability_pattern="create_draft",
                risk_level_override=RiskLevel.LOW,
                allowed=True,
                require_approval=False,
                enabled=True,
            )
        )
        db.commit()
        action = ExternalActionManager(db).create(
            company_id=company.id,
            integration_id=integration.id,
            capability="create_draft",
            payload={"to": ["x@example.com"], "subject": "S", "body": "B"},
            connection_id=connection.id,
        )
        assert action.status == ExternalActionStatus.SUCCEEDED
        assert _result(action)["draft"]["status"] == "draft"

    def test_intrinsically_approval_required_capability_never_auto_runs(self, db: Session) -> None:
        """send_message declares approval_required — a friendly policy can't waive it."""
        from app.db.models.external import (
            ExternalActionStatus,
            IntegrationPolicy,
            RiskLevel,
            ScopeType,
        )
        from app.external.action import ExternalActionManager
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)
        db.add(
            IntegrationPolicy(
                company_id=company.id,
                integration_id=integration.id,
                scope_type=ScopeType.COMPANY,
                capability_pattern="send_message",
                risk_level_override=RiskLevel.LOW,
                allowed=True,
                require_approval=False,
                enabled=True,
            )
        )
        db.commit()
        action = ExternalActionManager(db).create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={"to": ["x@example.com"], "subject": "S", "body": "B"},
            connection_id=connection.id,
        )
        assert action.status == ExternalActionStatus.AWAITING_APPROVAL


class TestCancel:
    def test_cancel_awaiting_action(self, db: Session) -> None:
        from app.db.models.external import ExternalActionStatus
        from app.external.action import ExternalActionManager

        company = _company(db)
        integration, connection = _email_setup(db, company.id)
        mgr = ExternalActionManager(db)
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={"to": ["x@example.com"], "subject": "S", "body": "B"},
            connection_id=connection.id,
        )
        assert action.status == ExternalActionStatus.AWAITING_APPROVAL
        cancelled = mgr.cancel(company.id, action.id)
        assert cancelled.status == ExternalActionStatus.CANCELLED
        assert cancelled.completed_at is not None

    def test_terminal_action_cannot_be_cancelled(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.result import ExternalActionError
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)
        mgr = ExternalActionManager(db)
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "campaign"},
            connection_id=connection.id,
        )
        assert action.status.value == "succeeded"
        try:
            mgr.cancel(company.id, action.id)
            raise AssertionError("A succeeded action cannot be cancelled")
        except ExternalActionError as exc:
            assert exc.code == "terminal"


class TestHttpFunnel:
    """The external-actions integration path over the HTTP API (HTTP-level)."""

    def _setup(self, api_client: TestClient, db: Session) -> tuple[str, str, str]:
        company = _company(db)
        cid = str(company.id)
        r = api_client.post(
            f"/api/v1/integrations/{cid}", json={"provider": "email", "name": "Email"}
        )
        assert r.status_code == 201, r.text
        iid = r.json()["id"]
        r = api_client.post(
            f"/api/v1/integrations/{cid}/{iid}/connections",
            json={
                "auth_method": "api_key",
                "secret_value": "mail-secret-9876543210",
                "scopes": ["email:send"],
                "permissions": ["email:send"],
            },
        )
        assert r.status_code == 201, r.text
        conn_id = r.json()["id"]
        return cid, iid, conn_id

    def test_full_send_flow_over_http(self, api_client: TestClient, db: Session) -> None:
        _reset_mailbox()
        cid, iid, conn_id = self._setup(api_client, db)
        body = {
            "integration_id": iid,
            "capability": "send_message",
            "action_type": "send_message",
            "connection_id": conn_id,
            "idempotency_key": "http-rfp-1",
            "payload": {"to": ["v@example.com"], "subject": "RFP", "body": "SOW"},
        }

        # 1. Create parks the approval-required action.
        r = api_client.post(f"/api/v1/external-actions/{cid}", json=body)
        assert r.status_code == 201, r.text
        parked = r.json()
        assert parked["status"] == "awaiting_approval"
        assert parked["approval_status"] == "pending"
        gate_id = parked["approval_gate_id"]
        assert gate_id

        # 2. The owner lists the journal; a foreign company cannot read it.
        r = api_client.get(f"/api/v1/external-actions/{cid}")
        assert r.status_code == 200
        assert any(a["id"] == parked["id"] for a in r.json())

        foreign = _company(db)
        r = api_client.get(f"/api/v1/external-actions/{foreign.id}/{parked['id']}")
        assert r.status_code == 404, r.text

        # 3. Approve through the Phase 9 gate router.
        r = api_client.post(
            f"/api/v1/autonomy/{cid}/approval-gates/{gate_id}/approve",
            json={"approver_id": None, "rationale": "canary — human approves"},
        )
        assert r.status_code == 200, r.text

        # 4. Replay with the approved gate → executed and verified, once.
        replay = dict(body)
        replay["approved_gate_id"] = gate_id
        r = api_client.post(f"/api/v1/external-actions/{cid}", json=replay)
        assert r.status_code == 201, r.text
        executed = r.json()
        assert executed["status"] == "succeeded", executed
        assert executed["approval_status"] == "approved"
        assert executed["verification"]["verified"] is True
        assert executed["result"]["message"]["status"] == "sent"
        assert _sent_count() == 1

        # 5. Duplicate replay of the same idempotency key is a conflict.
        r = api_client.post(f"/api/v1/external-actions/{cid}", json=replay)
        assert r.status_code == 409, r.text
        assert "Duplicate" in r.json()["detail"]

        # 6. A second send with the same (now-consumed) gate is a conflict.
        replay2 = dict(body)
        replay2["idempotency_key"] = "http-rfp-2"
        replay2["approved_gate_id"] = gate_id
        r = api_client.post(f"/api/v1/external-actions/{cid}", json=replay2)
        assert r.status_code == 409, r.text
        assert "gate_used" in r.json()["detail"]
        assert _sent_count() == 1

    def test_dashboard_aggregates(self, api_client: TestClient, db: Session) -> None:
        cid, iid, conn_id = self._setup(api_client, db)

        r = api_client.get(f"/api/v1/external-actions/{cid}/dashboard")
        assert r.status_code == 200
        assert r.json()["total_actions"] == 0

        r = api_client.post(
            f"/api/v1/external-actions/{cid}",
            json={
                "integration_id": iid,
                "capability": "send_message",
                "connection_id": conn_id,
                "payload": {"to": ["x@example.com"], "subject": "S", "body": "B"},
            },
        )
        assert r.status_code == 201
        assert r.json()["status"] == "awaiting_approval"

        r = api_client.get(f"/api/v1/external-actions/{cid}/dashboard")
        data = r.json()
        assert data["total_actions"] == 1
        assert data["pending_approval_count"] == 1
        assert data["pending_approvals"][0]["capability"] == "send_message"
