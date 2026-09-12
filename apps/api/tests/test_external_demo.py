"""Phase 10 external demo tests — three deterministic scenarios end-to-end (§68-70).

These tests mirror the seed_external_ops.py scenarios but as pytest tests.
All flows are deterministic (mock providers, in-memory email mailbox).
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy.orm import Session

_counter = 0


# ── Helpers ────────────────────────────────────────────────────────────────


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Demo Co {_counter}", description="unit")


def _employee(
    db: Session, company_id: UUID, name: str, role: str, permissions: list[str] | None = None
):
    """Create an AI employee carrying the given tool permissions."""
    from app.employee.manager import EmployeeManager

    grants = list(permissions or [])
    return EmployeeManager(db).create(name=name, role=role, tools=grants, permissions=grants)


def _allowlist_capability(
    db: Session,
    *,
    company_id: UUID,
    integration_id: UUID,
    capability_pattern: str,
) -> None:
    """Add an integration policy that lets a MEDIUM write auto-run.

    MEDIUM capabilities have risk_priority == 2 so they gate by default.
    This override lowers the effective risk to LOW for the named capability
    while leaving HIGH/CRITICAL (e.g. send_message) gated (§86 Rule 12).
    """
    from app.db.models.external import IntegrationPolicy, RiskLevel, ScopeType

    existing = db.execute(
        __import__("sqlalchemy")
        .select(IntegrationPolicy)
        .where(
            IntegrationPolicy.company_id == company_id,
            IntegrationPolicy.integration_id == integration_id,
            IntegrationPolicy.capability_pattern == capability_pattern,
            IntegrationPolicy.enabled.is_(True),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        IntegrationPolicy(
            company_id=company_id,
            integration_id=integration_id,
            scope_type=ScopeType.COMPANY,
            capability_pattern=capability_pattern,
            risk_level_override=RiskLevel.LOW,
            allowed=True,
            require_approval=False,
            enabled=True,
        )
    )
    db.commit()


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
        scopes=["email:send", "email:read"],
        permissions=["email:send", "email:read"],
    )
    return integration, connection


def _reset_mailbox():
    from app.external.providers import email as email_module

    email_module._MAILBOX.pop("email", None)
    email_module._SENT.pop("email", None)
    email_module._DRAFTS.pop("email", None)
    email_module._seed_mailbox("email")


def _memory_create(
    db: Session,
    *,
    namespace: str,
    content: str,
    summary: str,
    owner_id: UUID,
    source_type: str,
    source_id: str,
    importance: float = 0.7,
    confidence: float = 0.9,
):
    from app.db.models.memory import MemoryOwnerType, MemorySourceType, MemoryType
    from app.schemas.memory import MemoryCreate
    from app.services.memory_service import MemoryService

    source_type_map = {
        "browser_observation": MemorySourceType.TOOL_OUTPUT,
        "external_action": MemorySourceType.TOOL_OUTPUT,
    }
    return MemoryService(db).create(
        MemoryCreate(
            namespace=namespace,
            type=MemoryType.SEMANTIC,
            content=content,
            summary=summary,
            owner_type=MemoryOwnerType.SYSTEM,
            owner_id=None,
            source_type=source_type_map.get(source_type, MemorySourceType.TOOL_OUTPUT),
            source_id=UUID(source_id) if source_id else None,
            importance=importance,
            confidence=confidence,
        )
    )


# ── Tests ──────────────────────────────────────────────────────────────────


class TestExternalResearchDemo:
    """§68: Research Employee → browser research mission → observations → memory → verification."""

    def test_research_demo_end_to_end(self, db: Session) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN
        from app.external.browser.session import BrowserSessionManager
        from app.external.verification.helpers import verify_expected_text, verify_page_state
        from app.services.verification_service import VerificationService

        company = _company(db)
        employee = _employee(db, company.id, "Researcher", "researcher")

        # Setup browser session
        mgr = BrowserSessionManager(db)
        session = mgr.create(
            company_id=company.id, allowed_domains=[FIXTURE_DOMAIN], employee_id=employee.id
        )

        # Navigate to competitor pages
        home = f"https://{FIXTURE_DOMAIN}/"
        mgr.action(company.id, session.id, action_type="open_page", target={"url": home})

        # Extract text from competitor product page
        prod_page = f"https://{FIXTURE_DOMAIN}/products/nexus"
        mgr.action(company.id, session.id, action_type="open_page", target={"url": prod_page})

        extract = mgr.action(company.id, session.id, action_type="extract_text")
        result = json.loads(extract.result)
        assert "text" in result
        assert len(result["text"]) > 0

        # Extract links
        links = mgr.action(company.id, session.id, action_type="extract_links")
        link_result = json.loads(links.result)
        assert "links" in link_result
        assert isinstance(link_result["links"], list)

        # Verify observations are marked EXTERNAL_UNTRUSTED_CONTENT
        observations = mgr.observations(company.id, session.id)
        for obs in observations:
            assert obs.content_type.value == "external_untrusted_content"

        # Memory candidate stored
        memory = _memory_create(
            db,
            namespace="research",
            content=json.dumps({"text": result["text"][:500], "links": link_result["links"][:10]}),
            summary="Competitor product analysis from browser research",
            owner_id=company.id,
            source_type="browser_observation",
            source_id=str(session.id),
        )
        assert memory.id is not None

        # Verification — page observation matches expected URL
        verify_svc = VerificationService(db)
        outcome = verify_page_state(
            verify_svc, {"url": prod_page, "title": "NexusMirror"}, prod_page
        )
        assert outcome.verified is True

        # Expected text found
        text_outcome = verify_expected_text(verify_svc, result["text"], "nexus")
        assert text_outcome.verified is True


class TestDevelopmentOperationsDemo:
    """§69: Developer → devplatform.create_issue → verify → memory."""

    def test_devops_demo_end_to_end(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.integration import IntegrationService
        from app.external.verification.helpers import verify_issue_created
        from app.services.verification_service import VerificationService
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        employee = _employee(
            db,
            company.id,
            "Developer",
            "developer",
            ["development.create_issue", "development.get_issue"],
        )

        # Setup development integration
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="development", name="GitHub")
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value="gh-token-1234567890",
            env_var_hint="INTEGRATION_DEVELOPMENT_API_KEY",
            scopes=["repo:read", "repo:write", "issue:read", "issue:write"],
            permissions=["repo:read", "repo:write", "issue:read", "issue:write"],
        )

        # MEDIUM create_issue normally gates — allowlist so it auto-runs (§69)
        _allowlist_capability(
            db,
            company_id=company.id,
            integration_id=integration.id,
            capability_pattern="create_issue",
        )

        mgr = ExternalActionManager(db)

        # Create issue
        issue_action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="create_issue",
            payload={
                "repository": "nexus-core",
                "title": "Implement OAuth2",
                "body": "Add OAuth2 authentication",
                "labels": ["enhancement"],
            },
            action_type="create_issue",
            connection_id=connection.id,
            employee_id=employee.id,
        )
        assert issue_action.status.value == "succeeded"
        issue_result = json.loads(issue_action.result)
        assert issue_result["issue"]["title"] == "Implement OAuth2"
        issue_id = issue_result["issue"]["id"]

        # Verify issue exists via get_issue (LOW, auto-runs)
        get_action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="get_issue",
            payload={"issue_id": issue_id},
            action_type="get_issue",
            connection_id=connection.id,
            employee_id=employee.id,
        )
        assert get_action.status.value == "succeeded"
        fetched = json.loads(get_action.result)
        assert fetched["issue"]["id"] == issue_id

        # Verification
        verify_svc = VerificationService(db)
        outcome = verify_issue_created(verify_svc, issue_result, issue_id)
        assert outcome.verified is True

        # Memory candidate
        memory = _memory_create(
            db,
            namespace="development",
            content=json.dumps({"issue_id": issue_id, "title": "Implement OAuth2"}),
            summary="Created GitHub issue for OAuth2 implementation",
            owner_id=company.id,
            source_type="external_action",
            source_id=str(issue_action.id),
        )
        assert memory.id is not None


class TestEmailApprovalDemo:
    """§70: Marketing → create_draft (MEDIUM, allowlisted) → send_message (HIGH) parks for a
    human EXTERNAL_ACTION_APPROVAL gate → approved send → verify → audit.
    """

    def test_email_approval_demo_end_to_end(self, db: Session) -> None:
        from app.db.models.external import ExternalActionStatus
        from app.external.action import ExternalActionManager
        from app.external.integration import IntegrationService
        from app.external.verification.helpers import verify_message_sent
        from app.services.verification_service import VerificationService
        from app.startup.autonomy import AutonomyService
        from app.startup.gates import ApprovalGateManager

        _reset_mailbox()
        company = _company(db)
        # Autonomy enables low-risk external actions; send_message is HIGH +
        # intrinsically approval-required so it still parks for a human gate.
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        employee = _employee(
            db, company.id, "Marketer", "marketing", ["email.create_draft", "email.send_message"]
        )

        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value="mail-secret-9876543210",
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
            scopes=["email:send", "email:read"],
            permissions=["email:send", "email:read"],
        )

        # Allowlist create_draft (MEDIUM) so it auto-runs; send_message stays gated
        _allowlist_capability(
            db,
            company_id=company.id,
            integration_id=integration.id,
            capability_pattern="create_draft",
        )

        mgr = ExternalActionManager(db)

        # Step 1: Create draft (MEDIUM, allowlisted → auto-runs)
        draft_action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="create_draft",
            payload={
                "to": ["client@example.com"],
                "subject": "Proposal",
                "body": "Here is our proposal.",
            },
            action_type="create_draft",
            connection_id=connection.id,
            employee_id=employee.id,
        )
        assert draft_action.status.value == "succeeded"
        draft_result = json.loads(draft_action.result)
        assert draft_result["draft"]["status"] == "draft"
        draft_id = draft_result["draft"]["id"]

        # Step 2: Send message (HIGH risk, approval_required → parks)
        send_action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={
                "to": ["client@example.com"],
                "subject": "Proposal",
                "body": "Here is our proposal.",
                "draft_id": draft_id,
            },
            action_type="send_message",
            connection_id=connection.id,
            employee_id=employee.id,
        )
        assert send_action.status.value == "awaiting_approval"
        assert send_action.approval_status.value == "pending"
        assert send_action.approval_gate_id is not None
        gate_id = send_action.approval_gate_id

        # Step 3: Human approves the gate
        ApprovalGateManager(db).approve(company.id, gate_id, approver_id=None)

        # Step 4: Replay with approved gate → executes exactly once (Rule 12)
        executed = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={
                "to": ["client@example.com"],
                "subject": "Proposal",
                "body": "Here is our proposal.",
                "draft_id": draft_id,
            },
            action_type="send_message",
            connection_id=connection.id,
            approved_gate_id=gate_id,
            employee_id=employee.id,
        )
        assert executed.status == ExternalActionStatus.SUCCEEDED
        assert executed.approval_status.value == "approved"
        executed_result = json.loads(executed.result)
        assert executed_result["message"]["status"] == "sent"
        message_id = executed_result["message"]["id"]

        # Step 5: Verify the sent message
        verify_svc = VerificationService(db)
        outcome = verify_message_sent(verify_svc, executed_result, message_id)
        assert outcome.verified is True

        # Step 6: Memory candidate for the sent email
        memory = _memory_create(
            db,
            namespace="communications",
            content=json.dumps(
                {"to": ["client@example.com"], "subject": "Proposal", "status": "sent"}
            ),
            summary="Sent proposal email to client",
            owner_id=company.id,
            source_type="external_action",
            source_id=str(executed.id),
        )
        assert memory.id is not None

        # Audit trail — all three action statuses recorded
        journal = mgr.list_(company.id)
        statuses = sorted(a.status.value for a in journal)
        assert "succeeded" in statuses
        assert "awaiting_approval" in statuses
