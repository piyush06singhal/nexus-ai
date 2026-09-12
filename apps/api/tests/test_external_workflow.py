"""Phase 10 external workflow tests — EXTERNAL_ACTION workflow step end-to-end (§28).

The EXTERNAL_ACTION step runs one governed capability through the Phase 3 engine:
the step config carries ``company_id`` / ``integration_id`` / ``connection_id`` /
``capability`` (plus an optional ``approved_gate_id`` for operator resume), and the
engine forwards it to :class:`ExternalActionManager.create` so the full governance
funnel (permission → policy → risk → autonomy → approval → execute → verify →
recover → audit) is identical to a direct API/tool call.
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
    return CompanyManager(db).create(name=f"Wf Co {_counter}", description="unit")


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


def _sent_count() -> int:
    from app.external.providers import email as email_module

    return len(email_module._SENT.get("email", []))


def _external_config(
    company,
    integration,
    connection,
    *,
    capability: str,
    payload: dict,
    approved_gate_id: UUID | None = None,
) -> dict:
    """Build the EXTERNAL_ACTION step configuration the engine understands.

    Literal static inputs go in ``payload`` (the engine merges any resolved
    ``input_mapping`` on top); ``connection_id`` selects the credential-bound
    connection the provider authenticates with.
    """
    config = {
        "company_id": str(company.id),
        "integration_id": str(integration.id),
        "connection_id": str(connection.id),
        "capability": capability,
        "payload": payload,
    }
    if approved_gate_id is not None:
        config["approved_gate_id"] = str(approved_gate_id)
    return config


class TestExternalActionWorkflowStep:
    def test_workflow_step_type_external_action_exists(self, db: Session) -> None:
        from app.db.models.workflow import WorkflowStepType

        # The enum should have EXTERNAL_ACTION value
        assert "EXTERNAL_ACTION" in WorkflowStepType.__members__

    def test_external_action_step_config_validation(self, db: Session) -> None:
        from app.db.models.workflow import WorkflowStep, WorkflowStepType
        from app.workflow.validator import validate_workflow_steps

        company = _company(db)
        integration, connection = _email_setup(db, company.id)

        step_config = {
            "type": "external_action",
            "company_id": str(company.id),
            "capability": "send_message",
            "integration_id": str(integration.id),
            "connection_id": str(connection.id),
            "input_mapping": {
                "to": ["recipient@example.com"],
                "subject": "Workflow Email",
                "body": "Sent from workflow",
            },
        }

        step = WorkflowStep(
            name="step-1",
            step_type=WorkflowStepType.EXTERNAL_ACTION,
            configuration=json.dumps(step_config),
        )
        # Should validate without error
        result = validate_workflow_steps([step])
        assert len(result.errors) == 0

    def test_external_action_step_missing_required_fields(self, db: Session) -> None:
        from app.db.models.workflow import WorkflowStep, WorkflowStepType
        from app.workflow.validator import validate_workflow_steps

        _company(db)

        step_config = {
            "type": "external_action",
            # Missing capability, integration_id, connection_id (and company_id)
        }

        step = WorkflowStep(
            name="step-1",
            step_type=WorkflowStepType.EXTERNAL_ACTION,
            configuration=json.dumps(step_config),
        )
        result = validate_workflow_steps([step])
        assert len(result.errors) > 0
        assert any("capability" in e.lower() for e in result.errors)

    def test_external_action_step_execution(self, db: Session) -> None:
        from app.db.models.external import ExternalActionStatus
        from app.db.models.workflow import WorkflowStepType
        from app.external.action import ExternalActionManager
        from app.schemas.workflow import WorkflowCreate, WorkflowStepCreate
        from app.services.workflow_service import WorkflowService
        from app.startup.autonomy import AutonomyService
        from app.workflow.engine import WorkflowEngine

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        # A low-risk read (search_messages) is the deterministically auto-runnable
        # capability: HIGH/critical capabilities (e.g. send_message) stay gated by
        # design (proven in test_external_actions.py), so they cannot be driven to
        # SUCCEEDED in a single autonomous engine run.
        svc = WorkflowService(db)
        workflow = svc.create(WorkflowCreate(name="Test External Action Workflow"))
        svc.add_step(
            workflow.id,
            WorkflowStepCreate(
                name="step-1",
                step_type=WorkflowStepType.EXTERNAL_ACTION,
                configuration=_external_config(
                    company,
                    integration,
                    connection,
                    capability="search_messages",
                    payload={"query": "campaign"},
                ),
            ),
        )
        svc.activate(workflow.id)
        execution = svc.create_execution(workflow.id, trigger_type="manual")

        # Execute the workflow
        engine = WorkflowEngine(db)
        engine.execute(execution.id)

        # Verify the external action was created and succeeded
        actions = ExternalActionManager(db).list_(company.id)
        assert len(actions) >= 1
        search_actions = [a for a in actions if a.capability == "search_messages"]
        assert len(search_actions) == 1
        assert search_actions[0].status == ExternalActionStatus.SUCCEEDED

    def test_external_action_step_with_gate_approval(self, db: Session) -> None:
        """When capability requires approval, step should park awaiting approval."""
        from app.db.models.external import ExternalActionStatus
        from app.db.models.workflow import WorkflowStepType
        from app.external.action import ExternalActionManager
        from app.schemas.workflow import WorkflowCreate, WorkflowStepCreate
        from app.services.workflow_service import WorkflowService
        from app.startup.gates import ApprovalGateManager
        from app.workflow.engine import WorkflowEngine

        _reset_mailbox()
        company = _company(db)
        # NO allow_matrix - default requires approval
        svc = WorkflowService(db)
        integration, connection = _email_setup(db, company.id)
        workflow = svc.create(WorkflowCreate(name="Gated Workflow"))
        send_payload = {
            "to": ["gated@example.com"],
            "subject": "Gated",
            "body": "Needs approval",
        }
        step = svc.add_step(
            workflow.id,
            WorkflowStepCreate(
                name="step-1",
                step_type=WorkflowStepType.EXTERNAL_ACTION,
                configuration=_external_config(
                    company,
                    integration,
                    connection,
                    capability="send_message",
                    payload=send_payload,
                ),
            ),
        )
        svc.activate(workflow.id)
        execution = svc.create_execution(workflow.id, trigger_type="manual")

        engine = WorkflowEngine(db)
        engine.execute(execution.id)

        # Action should be awaiting approval
        actions = ExternalActionManager(db).list_(company.id)
        send_actions = [a for a in actions if a.capability == "send_message"]
        assert len(send_actions) == 1
        assert send_actions[0].status == ExternalActionStatus.AWAITING_APPROVAL
        assert send_actions[0].approval_gate_id is not None

        # Approve the gate and re-run the step through the engine with the
        # approved gate id — one approved gate authorizes exactly one execution.
        gate_id = send_actions[0].approval_gate_id
        ApprovalGateManager(db).approve(company.id, gate_id)

        step.configuration = json.dumps(
            _external_config(
                company,
                integration,
                connection,
                capability="send_message",
                payload=send_payload,
                approved_gate_id=gate_id,
            )
        )
        db.commit()

        execution = svc.create_execution(workflow.id, trigger_type="manual")
        engine.execute(execution.id)

        executed = [
            a
            for a in ExternalActionManager(db).list_(company.id)
            if a.capability == "send_message" and a.status == ExternalActionStatus.SUCCEEDED
        ]
        assert len(executed) == 1
        assert executed[0].approval_gate_id == gate_id
        # The side effect ran exactly once.
        assert _sent_count() == 1


class TestWorkflowOrchestrationWithExternalActions:
    def test_orchestration_can_coordinate_external_actions(self, db: Session) -> None:
        from app.db.models.external import (
            ExternalActionStatus,
            IntegrationPolicy,
            RiskLevel,
            ScopeType,
        )
        from app.db.models.workflow import WorkflowStepType
        from app.external.action import ExternalActionManager
        from app.schemas.workflow import WorkflowCreate, WorkflowStepCreate
        from app.services.workflow_service import WorkflowService
        from app.startup.autonomy import AutonomyService
        from app.workflow.engine import WorkflowEngine

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        # create_draft is MEDIUM risk — permit it to auto-run so the multi-step
        # workflow completes autonomously (proven pattern from
        # test_external_actions.py::test_policy_override_downgrades_medium_capability_to_allowed).
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

        # Workflow with multiple external action steps
        svc = WorkflowService(db)
        workflow = svc.create(WorkflowCreate(name="Multi-step External Workflow"))
        svc.add_step(
            workflow.id,
            WorkflowStepCreate(
                name="step-1",
                step_type=WorkflowStepType.EXTERNAL_ACTION,
                configuration=_external_config(
                    company,
                    integration,
                    connection,
                    capability="create_draft",
                    payload={
                        "to": ["draft@example.com"],
                        "subject": "Draft from workflow",
                        "body": "Draft body",
                    },
                ),
            ),
        )
        svc.add_step(
            workflow.id,
            WorkflowStepCreate(
                name="step-2",
                step_type=WorkflowStepType.EXTERNAL_ACTION,
                configuration=_external_config(
                    company,
                    integration,
                    connection,
                    capability="search_messages",
                    payload={"query": "draft"},
                ),
            ),
        )
        svc.activate(workflow.id)
        execution = svc.create_execution(workflow.id, trigger_type="manual")

        engine = WorkflowEngine(db)
        engine.execute(execution.id)

        # Both actions should have succeeded
        actions = ExternalActionManager(db).list_(company.id)
        create_draft_actions = [a for a in actions if a.capability == "create_draft"]
        search_actions = [a for a in actions if a.capability == "search_messages"]

        assert len(create_draft_actions) == 1
        assert create_draft_actions[0].status == ExternalActionStatus.SUCCEEDED
        assert len(search_actions) == 1
        assert search_actions[0].status == ExternalActionStatus.SUCCEEDED


class TestWorkflowStepTypeRegistration:
    def test_external_action_registered_in_tool_registry(self, db: Session) -> None:
        from app.tools.registry import tool_exists

        # External action capabilities should be registered as tools
        assert tool_exists("email.send_message")
        assert tool_exists("email.search_messages")
        assert tool_exists("email.create_draft")
        assert tool_exists("email.get_message")
