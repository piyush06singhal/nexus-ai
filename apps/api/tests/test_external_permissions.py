"""Phase 10 external permissions tests — capability allow/deny, dangerous-tool
permission via Phase 2, employee/agent permission context, scope restriction,
and cross-company 404 isolation (§75 Permissions).
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
    return CompanyManager(db).create(name=f"Perm Co {_counter}", description="unit")


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


class TestCapabilityAllowedDenied:
    def test_allowed_capability_runs_when_policy_allows(self, db: Session) -> None:
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

    def test_denied_capability_is_blocked_by_policy(self, db: Session) -> None:
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


class TestDangerousToolPermission:
    def test_high_risk_capability_tool_is_dangerous(self, db: Session) -> None:
        from app.tools.registry import get_tool, tool_exists

        # The email.send_message tool should be registered as dangerous=True
        assert tool_exists("email.send_message"), "email.send_message tool must be registered"
        tool_def = get_tool("email.send_message").definition
        assert tool_def.dangerous is True, "HIGH risk capability tools must be dangerous=True"

    def test_low_risk_capability_tool_not_dangerous(self, db: Session) -> None:
        from app.tools.registry import get_tool, tool_exists

        assert tool_exists("email.search_messages"), "email.search_messages tool must be registered"
        tool_def = get_tool("email.search_messages").definition
        assert tool_def.dangerous is False, "LOW risk capability tools must be dangerous=False"

    def test_agent_without_permission_cannot_call_dangerous_tool(self, db: Session) -> None:
        from app.employee.manager import EmployeeManager
        from app.tools.permissions import PermissionContext, check_permission
        from app.tools.registry import get_tool

        # Create an employee without the email.send permission: only search is granted.
        emp_mgr = EmployeeManager(db)
        employee = emp_mgr.create(
            name="NoPerm Employee",
            role="assistant",
            permissions=["email:search"],
            tools=["email.search_messages"],
        )

        # The agent's tool permissions (from the employee) don't include
        # email.send_message, so the dangerous tool must not be executable.
        allowed_tools = set(json.loads(employee.tools or "[]"))
        assert "email.send_message" not in allowed_tools

        send_def = get_tool("email.send_message").definition
        search_def = get_tool("email.search_messages").definition
        assert send_def.dangerous is True

        context = PermissionContext(agent_id=employee.agent_id, allowed_tools=allowed_tools)
        # Denied: dangerous tool is not in the agent's allowlist.
        assert check_permission(send_def, context) is False
        # Sanity: the granted (non-dangerous) tool is still allowed.
        assert check_permission(search_def, context) is True
        # Explicitly granting the dangerous tool is required to flip the verdict:
        # dangerous tools need an explicit allow in the allowlist, not just the
        # absence of a deny.
        granted = PermissionContext(
            agent_id=employee.agent_id,
            allowed_tools=allowed_tools | {"email.send_message"},
        )
        assert check_permission(send_def, granted) is True


class TestEmployeeAgentPermissionContext:
    def test_employee_with_tool_permission_can_execute(self, db: Session) -> None:
        from app.employee.manager import EmployeeManager
        from app.tools.permissions import PermissionContext, check_permission
        from app.tools.registry import get_tool

        emp_mgr = EmployeeManager(db)
        employee = emp_mgr.create(
            name="Permitted Employee",
            role="assistant",
            permissions=["email:send", "email:search"],
            tools=["email.send_message", "email.search_messages"],
        )
        # Employee has the permissions - integration checks would pass
        permissions = json.loads(employee.permissions or "[]")
        assert "email:send" in permissions
        tools = json.loads(employee.tools or "[]")
        assert "email.send_message" in tools
        # A permission context built from the employee's grants lets both the
        # low-risk and the dangerous tool execute.
        context = PermissionContext(agent_id=employee.agent_id, allowed_tools=set(tools))
        assert check_permission(get_tool("email.send_message").definition, context) is True
        assert check_permission(get_tool("email.search_messages").definition, context) is True

    def test_agent_inherits_employee_permissions(self, db: Session) -> None:
        from app.db.models.agent import Agent
        from app.employee.manager import EmployeeManager

        emp_mgr = EmployeeManager(db)
        employee = emp_mgr.create(
            name="Agent Owner",
            role="lead",
            permissions=["email:send"],
            tools=["email.send_message"],
        )

        # An agent created for this employee would inherit the permissions
        # through the employee's tool permissions list — the employee has an
        # auto-created backing agent that carries the grants.
        assert employee.agent_id is not None
        backing = db.get(Agent, employee.agent_id)
        assert backing is not None
        assert json.loads(employee.tools or "[]") == ["email.send_message"]
        assert json.loads(employee.permissions or "[]") == ["email:send"]


class TestScopeRestriction:
    def test_integration_policy_at_department_scope(self, db: Session) -> None:
        from app.company.departments import DepartmentManager
        from app.db.models.external import (
            ExternalActionStatus,
            IntegrationPolicy,
            RiskLevel,
            ScopeType,
        )
        from app.external.action import ExternalActionManager
        from app.external.integration import IntegrationService
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        dept = DepartmentManager(db).create(company_id=company.id, name="Email Ops")
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value="mail-secret-9876543210",
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
        )

        # A policy scoped to a department waives approval for a MEDIUM write:
        # effective risk is downgraded to LOW and require_approval=False, so
        # the capability auto-runs. Pattern matching is exact (or `*` / `..*`),
        # so `create_draft` matches `create_draft`.
        db.add(
            IntegrationPolicy(
                company_id=company.id,
                integration_id=integration.id,
                scope_type=ScopeType.DEPARTMENT,
                scope_id=dept.id,
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


class TestCrossCompanyIsolation:
    def test_external_action_cross_company_404(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.result import ExternalActionError

        a, b = _company(db), _company(db)
        integration, connection = _email_setup(db, a.id)

        # Create an action in company A
        action = ExternalActionManager(db).create(
            company_id=a.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "test"},
            connection_id=connection.id,
        )

        # Try to read from company B - should fail
        try:
            ExternalActionManager(db).get(b.id, action.id)
            raise AssertionError("Foreign-company action must not be readable")
        except ExternalActionError as exc:
            assert exc.code == "not_found"

    def test_browser_session_cross_company_404(self, db: Session) -> None:
        from app.external.browser.session import BrowserSessionManager
        from app.external.types import ExternalValidationFailure

        a, b = _company(db), _company(db)
        mgr = BrowserSessionManager(db)
        session = mgr.create(company_id=a.id, allowed_domains=["example.com"])

        try:
            mgr.get(b.id, session.id)
            raise AssertionError("Foreign-company browser session must not be readable")
        except ExternalValidationFailure:
            pass

    def test_computer_session_cross_company_404(self, db: Session) -> None:
        from app.external.computer.session import ComputerSessionManager
        from app.external.types import ExternalValidationFailure

        a, b = _company(db), _company(db)
        mgr = ComputerSessionManager(db)
        session = mgr.create(company_id=a.id)

        try:
            mgr.get(b.id, session.id)
            raise AssertionError("Foreign-company computer session must not be readable")
        except ExternalValidationFailure:
            pass

    def test_integration_cross_company_404(self, db: Session) -> None:
        from app.external.integration import IntegrationNotFoundError, IntegrationService

        a, b = _company(db), _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=a.id, provider="email", name="Email")

        try:
            svc.get(b.id, integration.id)
            raise AssertionError("Foreign-company integration must not be readable")
        except IntegrationNotFoundError:
            pass

    def test_connection_cross_company_404(self, db: Session) -> None:
        from app.external.integration import IntegrationService
        from app.external.types import ExternalValidationFailure

        a, b = _company(db), _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=a.id, provider="email", name="Email")
        connection = svc.connect(
            company_id=a.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value="mail-secret-9876543210",
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
        )

        try:
            svc.get_connection(b.id, connection.id)
            raise AssertionError("Foreign-company connection must not be readable")
        except ExternalValidationFailure:
            pass
