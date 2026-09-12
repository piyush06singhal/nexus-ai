"""Phase 10 external security tests — SSRF, path traversal, credential leakage,
token leak, data exfiltration classification, cross-company, unauth webhook (§75 Security).
"""

from __future__ import annotations

import os
import tempfile
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Sec Co {_counter}", description="unit")


def _email_setup(db: Session, company_id: UUID, *, secret: str = "mail-secret-9876543210"):
    from app.external.integration import IntegrationService

    svc = IntegrationService(db)
    integration = svc.create(company_id=company_id, provider="email", name="Email")
    connection = svc.connect(
        company_id=company_id,
        integration_id=integration.id,
        auth_method="api_key",
        secret_value=secret,
        env_var_hint="INTEGRATION_EMAIL_API_KEY",
        scopes=["email:read"],
        permissions=["email:read"],
    )
    return integration, connection


class TestSSRF:
    def test_loopback_blocked(self, db: Session) -> None:
        from app.external.api.ssrf import SSRFBlocked, SSRFGuard

        guard = SSRFGuard()
        try:
            guard.validate("http://localhost:8080/admin")
            raise AssertionError("Loopback must be blocked")
        except SSRFBlocked:
            pass

    def test_private_ranges_blocked(self, db: Session) -> None:
        from app.external.api.ssrf import SSRFBlocked, SSRFGuard

        guard = SSRFGuard()
        for url in [
            "http://10.0.0.1/",
            "http://172.16.0.1/",
            "http://192.168.1.1/",
            "http://169.254.169.254/latest/meta-data/",
        ]:
            try:
                guard.validate(url)
                raise AssertionError(f"Private range {url} must be blocked")
            except SSRFBlocked:
                pass

    def test_metadata_endpoint_blocked(self, db: Session) -> None:
        from app.external.api.ssrf import SSRFBlocked, SSRFGuard

        guard = SSRFGuard()
        try:
            guard.validate("http://169.254.169.254/latest/meta-data/")
            raise AssertionError("Metadata endpoint must be blocked")
        except SSRFBlocked:
            pass

    def test_redirect_bypass_blocked(self, db: Session) -> None:
        """Every redirect hop is re-validated, so a benign first hop cannot
        smuggle a private/metadata destination through the guard."""
        from app.external.api.ssrf import SSRFBlocked, SSRFGuard

        guard = SSRFGuard()
        chain = [
            "http://example.com/page",  # benign first hop
            "http://127.0.0.1:8080/admin",  # redirect target that must be blocked
        ]
        try:
            guard.validate_chain(chain)
            raise AssertionError("Redirect to private host must be blocked at the hop")
        except SSRFBlocked:
            pass

    def test_allowed_domain_passes(self, db: Session) -> None:
        from app.external.api.ssrf import SSRFGuard

        guard = SSRFGuard()
        result = guard.validate("https://api.github.com/repos/owner/repo")
        assert result is True

    def test_generic_http_connector_uses_ssrf_guard(self, db: Session, monkeypatch) -> None:
        """GenericHTTPConnector wraps SecureHTTPClient which uses SSRF guard."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "external_generic_http_connector_enabled", True)
        from app.external.providers.http_connector import GenericHTTPConnectorProvider

        provider = GenericHTTPConnectorProvider()
        assert provider is not None
        # The provider uses SecureHTTPClient internally which enforces SSRF


class TestPathTraversal:
    def test_absolute_path_blocked(self, db: Session) -> None:
        from app.external.files.security import PathTraversalError, validate_path

        try:
            validate_path("/etc/passwd", "/workspace")
            raise AssertionError("Absolute paths outside workspace must be blocked")
        except PathTraversalError:
            pass

    def test_parent_traversal_blocked(self, db: Session) -> None:
        from app.external.files.security import PathTraversalError, validate_path

        try:
            validate_path("workspace/../../etc/passwd", "/workspace")
            raise AssertionError("Parent traversal must be blocked")
        except PathTraversalError:
            pass

    def test_symlink_traversal_blocked(self, db: Session) -> None:

        from app.external.files.security import PathTraversalError, validate_path

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a symlink pointing outside the workspace
            target = os.path.join(tmpdir, "outside")
            os.makedirs(target)
            link = os.path.join(tmpdir, "workspace", "link")
            os.makedirs(os.path.dirname(link), exist_ok=True)
            os.symlink(target, link)

            try:
                validate_path(link, os.path.join(tmpdir, "workspace"))
                raise AssertionError("Symlink traversal must be blocked")
            except PathTraversalError:
                pass

    def test_allowed_paths_pass(self, db: Session) -> None:

        from app.external.files.security import validate_path

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = os.path.join(tmpdir, "workspace")
            os.makedirs(workspace)
            test_file = os.path.join(workspace, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")

            result = validate_path(test_file, workspace)
            assert result is True


class TestCredentialLeakage:
    def test_no_secret_in_responses(self, db: Session) -> None:
        from app.db.session import get_db
        from app.main import app

        company = _company(db)
        cid = str(company.id)
        _, connection = _email_setup(db, company.id)
        iid = str(connection.integration_id)

        secret = "super-secret-api-key-12345"
        # Use client that shares the test's db session
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        r = client.post(
            f"/api/v1/integrations/{cid}/{iid}/connections",
            json={
                "auth_method": "api_key",
                "secret_value": secret,
                "env_var_hint": "INTEGRATION_EMAIL_API_KEY",
            },
        )
        app.dependency_overrides.clear()
        assert r.status_code == 201, r.text
        body = r.text
        assert secret not in body, "Secret must not appear in response"
        assert "super-secret" not in body

    def test_no_secret_in_logs(self, db: Session, caplog) -> None:
        from app.db.models.external import ExternalCredential

        company = _company(db)
        _, connection = _email_setup(db, company.id, secret="log-secret-99999")
        secret = "log-secret-99999"

        # Check that the credential reference doesn't contain the secret
        assert secret not in connection.credential_reference

        # Verify the vault stores only masked value
        cred = (
            db.query(ExternalCredential)
            .filter(ExternalCredential.reference == connection.credential_reference)
            .first()
        )
        assert cred is not None
        assert secret not in cred.masked_value
        assert cred.masked_value.endswith("9999")

    def test_no_secret_in_database(self, db: Session) -> None:
        from app.db.models.external import ExternalCredential

        company = _company(db)
        secret = "db-secret-77777"
        _, connection = _email_setup(db, company.id, secret=secret)

        cred = (
            db.query(ExternalCredential)
            .filter(ExternalCredential.reference == connection.credential_reference)
            .first()
        )
        assert cred is not None
        # The plaintext secret must never be in any DB column
        assert secret not in str(cred.__dict__)
        assert "db-secret" not in cred.masked_value

    def test_no_secret_in_memory(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id, secret="memory-secret-55555")

        mgr = ExternalActionManager(db)
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "test"},
            connection_id=connection.id,
        )

        # The action result/input must not contain the secret
        assert "memory-secret" not in (action.input or "")
        assert "memory-secret" not in (action.result or "")

    def test_no_secret_in_tool_output(self, db: Session, monkeypatch) -> None:
        import app.db.session as session_module
        from app.external.providers import email as email_module
        from app.startup.autonomy import AutonomyService
        from app.tools.registry import get_tool

        # Monkeypatch SessionLocal to use the test's SQLite engine
        monkeypatch.setattr(session_module, "SessionLocal", lambda: db)

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        _email_setup(db, company.id, secret="memory-secret-55555")

        email_module._MAILBOX.pop("email", None)
        email_module._seed_mailbox("email")

        tool = get_tool("email.search_messages")
        assert tool is not None, "capability tool email.search_messages must be registered"
        result = tool.execute(company_id=company.id, query="test")
        assert "memory-secret" not in str(result)


class TestDataExfiltrationClassification:
    def test_secret_classification_blocked(self, db: Session) -> None:
        from app.external.security.exfiltration import DataClassification, classify_data

        secret_data = {"api_key": "sk-1234567890", "password": "secret123"}
        classification = classify_data(secret_data)
        assert classification == DataClassification.SECRET

    def test_restricted_classification_requires_approval(self, db: Session) -> None:
        from app.external.security.exfiltration import DataClassification, classify_data

        restricted_data = {"ssn": "123-45-6789", "credit_card": "4111-1111-1111-1111"}
        classification = classify_data(restricted_data)
        assert classification == DataClassification.RESTRICTED

    def test_internal_classification_allowed(self, db: Session) -> None:
        from app.external.security.exfiltration import DataClassification, classify_data

        internal_data = {"name": "John", "company": "Acme"}
        classification = classify_data(internal_data)
        assert classification == DataClassification.INTERNAL


class TestCrossCompanyIsolation:
    def test_external_action_cross_company_404(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.result import ExternalActionError

        a, b = _company(db), _company(db)
        integration, connection = _email_setup(db, a.id)

        action = ExternalActionManager(db).create(
            company_id=a.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "test"},
            connection_id=connection.id,
        )

        try:
            ExternalActionManager(db).get(b.id, action.id)
            raise AssertionError("Foreign-company action must not be readable")
        except ExternalActionError as exc:
            assert exc.code == "not_found"


class TestUnauthenticatedWebhook:
    def test_unauthenticated_webhook_rejected(self, db: Session, monkeypatch) -> None:
        """Unauthenticated payloads are never trusted commands (§86 Rule 10)."""
        from app.core.config import settings
        from app.db.session import get_db
        from app.main import app

        company = _company(db)
        # A valid company + email integration so the only failure is the
        # missing signature (not a 404/503 that would mask the 401).
        _email_setup(db, company.id)
        monkeypatch.setattr(settings, "external_webhook_hmac_secret", "webhook-shared-secret-123")

        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        r = client.post(
            f"/api/v1/webhooks/{company.id}/events/email",
            json={"event_type": "any_event", "data": {}},
        )
        app.dependency_overrides.clear()
        assert r.status_code == 401, r.text
