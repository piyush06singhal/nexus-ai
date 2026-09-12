"""Phase 10 external verification tests — create→verify, update→verify, delete→verify,
send→verify via helpers (§75 Verification).
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Verify Co {_counter}", description="unit")


def _email_setup(db: Session, company_id: UUID):
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


def _reset_mailbox():
    from app.external.providers import email as email_module

    email_module._MAILBOX.pop("email", None)
    email_module._SENT.pop("email", None)
    email_module._DRAFTS.pop("email", None)
    email_module._seed_mailbox("email")


class TestVerificationHelpers:
    def test_verify_resource_created(self, db: Session) -> None:
        from app.external.verification.helpers import verify_resource_created
        from app.services.verification_service import VerificationService

        svc = VerificationService(db)
        result = {"id": "res-123", "name": "Test Resource", "status": "created"}

        outcome = verify_resource_created(svc, result, "test_resource", "res-123")
        assert outcome.verified is True

    def test_verify_resource_updated(self, db: Session) -> None:
        from app.external.verification.helpers import verify_resource_updated
        from app.services.verification_service import VerificationService

        svc = VerificationService(db)
        before = {"id": "res-123", "name": "Old Name", "version": 1}
        after = {"id": "res-123", "name": "New Name", "version": 2}

        outcome = verify_resource_updated(svc, before, after, "test_resource", "res-123")
        assert outcome.verified is True

    def test_verify_resource_deleted(self, db: Session) -> None:
        from app.external.verification.helpers import verify_resource_deleted
        from app.services.verification_service import VerificationService

        svc = VerificationService(db)
        result = {"id": "res-123", "deleted": True}

        outcome = verify_resource_deleted(svc, result, "test_resource", "res-123")
        assert outcome.verified is True

    def test_verify_message_sent(self, db: Session) -> None:
        from app.external.verification.helpers import verify_message_sent
        from app.services.verification_service import VerificationService

        svc = VerificationService(db)
        result = {"message": {"id": "msg-123", "status": "sent", "to": ["x@example.com"]}}

        outcome = verify_message_sent(svc, result, "msg-123")
        assert outcome.verified is True

    def test_verify_event_created(self, db: Session) -> None:
        from app.external.verification.helpers import verify_event_created
        from app.services.verification_service import VerificationService

        svc = VerificationService(db)
        result = {"event": {"id": "evt-123", "type": "meeting", "status": "created"}}

        outcome = verify_event_created(svc, result, "evt-123")
        assert outcome.verified is True

    def test_verify_issue_created(self, db: Session) -> None:
        from app.external.verification.helpers import verify_issue_created
        from app.services.verification_service import VerificationService

        svc = VerificationService(db)
        result = {"issue": {"id": "issue-123", "title": "Bug", "state": "open"}}

        outcome = verify_issue_created(svc, result, "issue-123")
        assert outcome.verified is True

    def test_verify_page_state(self, db: Session) -> None:
        from app.external.verification.helpers import verify_page_state
        from app.services.verification_service import VerificationService

        svc = VerificationService(db)
        page = {"url": "https://example.com/", "title": "Example", "visible_text": "Example Domain"}

        outcome = verify_page_state(svc, page, "https://example.com/", expected_title="Example")
        assert outcome.verified is True

    def test_verify_expected_text(self, db: Session) -> None:
        from app.external.verification.helpers import verify_expected_text
        from app.services.verification_service import VerificationService

        svc = VerificationService(db)
        text = "Welcome to NEXUS Mirror"
        expected = "NEXUS"

        outcome = verify_expected_text(svc, text, expected)
        assert outcome.verified is True


class TestExternalActionVerification:
    def test_send_message_verified_on_success(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.integration import IntegrationService
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value="mail-secret-9876543210",
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
            scopes=["email:send"],
            permissions=["email:send"],
        )

        mgr = ExternalActionManager(db)
        # send_message is HIGH and intrinsically approval-required, so even with
        # the allow_matrix it parks for a human gate on the first create.
        parked = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={"to": ["x@example.com"], "subject": "Test", "body": "Body"},
            action_type="send_message",
            connection_id=connection.id,
        )
        assert parked.status.value == "awaiting_approval"
        assert parked.approval_gate_id is not None

        # Approve the gate, then replay the same payload with the gate id —
        # the gate authorizes exactly one action once (Rule 12).
        from app.startup.gates import ApprovalGateManager

        ApprovalGateManager(db).approve(company.id, parked.approval_gate_id)
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={"to": ["x@example.com"], "subject": "Test", "body": "Body"},
            action_type="send_message",
            connection_id=connection.id,
            approved_gate_id=parked.approval_gate_id,
        )

        assert action.status.value == "succeeded"
        result = json.loads(action.result)
        assert result["message"]["status"] == "sent"
        assert action.verification is not None
        verification = json.loads(action.verification)
        assert verification["verified"] is True

    def test_create_draft_verified(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.integration import IntegrationService
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value="mail-secret-9876543210",
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
        )

        mgr = ExternalActionManager(db)
        # create_draft is a MEDIUM write whose intent escalation (and the
        # startup high-risk rule) requires approval by default, so it parks
        # like send_message until a human approves the gate.
        parked = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="create_draft",
            payload={"to": ["x@example.com"], "subject": "Draft", "body": "Body"},
            connection_id=connection.id,
        )
        assert parked.status.value == "awaiting_approval"
        assert parked.approval_gate_id is not None

        from app.startup.gates import ApprovalGateManager

        ApprovalGateManager(db).approve(company.id, parked.approval_gate_id)
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="create_draft",
            payload={"to": ["x@example.com"], "subject": "Draft", "body": "Body"},
            connection_id=connection.id,
            approved_gate_id=parked.approval_gate_id,
        )

        assert action.status.value == "succeeded"
        result = json.loads(action.result)
        assert result["draft"]["status"] == "draft"
        assert action.verification is not None
        verification = json.loads(action.verification)
        assert verification["verified"] is True

    def test_search_messages_verified(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.integration import IntegrationService
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value="mail-secret-9876543210",
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
        )

        mgr = ExternalActionManager(db)
        # LOW-risk read with an allow_matrix allow auto-runs. The query must
        # actually match a seeded mock message ("campaign" → msg-001) so the
        # result carries a read-back id and verification is performed.
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "campaign"},
            connection_id=connection.id,
        )

        assert action.status.value == "succeeded"
        result = json.loads(action.result)
        assert any(m["id"] == "msg-001" for m in result["messages"])
        assert action.verification is not None
        verification = json.loads(action.verification)
        assert verification["verified"] is True


class TestVerificationFailure:
    def test_verification_fails_when_expected_not_found(self, db: Session) -> None:
        from app.external.verification.helpers import verify_expected_text
        from app.services.verification_service import VerificationService

        svc = VerificationService(db)
        text = "No match here"
        expected = "NEXUS"

        outcome = verify_expected_text(svc, text, expected)
        assert outcome.verified is False
