"""Phase 10 integration lifecycle tests — the IntegrationService surface (§47).

Covers provider-backed integration CRUD, capability materialization (each
provider capability becomes an ``integration_capabilities`` row), the
reference-only connect flow (commands carry a one-shot secret that is never
persisted), test (no secrets returned), revoke, invalid provider, and the
cross-company 404 isolation that every read/action enforces.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Integration Co {_counter}", description="unit")


class TestCreate:
    def test_create_email_integration_materializes_capabilities(self, db: Session) -> None:
        from app.db.models.external import IntegrationCategory, IntegrationStatus
        from app.external.integration import IntegrationService

        company = _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Company Email")
        assert integration.provider == "email"
        assert integration.status == IntegrationStatus.AVAILABLE
        assert integration.category == IntegrationCategory.COMMUNICATION

        caps = svc.capabilities(company.id, integration.id)
        names = sorted(c.name for c in caps)
        assert names == ["create_draft", "get_message", "search_messages", "send_message"]
        by_name = {c.name: c for c in caps}
        assert by_name["send_message"].risk_level.value == "high"
        assert by_name["send_message"].approval_required is True
        assert by_name["send_message"].reversibility.value == "irreversible"
        assert by_name["search_messages"].risk_level.value == "low"

    def test_unknown_provider_is_rejected(self, db: Session) -> None:
        from app.external.integration import IntegrationService

        company = _company(db)
        svc = IntegrationService(db)
        try:
            svc.create(company_id=company.id, provider="does_not_exist", name="Nope")
            raise AssertionError("Unknown provider must be rejected")
        except KeyError:
            pass

    def test_development_and_web_research_providers(self, db: Session) -> None:
        from app.external.integration import IntegrationService

        company = _company(db)
        svc = IntegrationService(db)
        dev = svc.create(company_id=company.id, provider="development", name="GitHub")
        web = svc.create(company_id=company.id, provider="web_research", name="Web")
        assert {c.name for c in svc.capabilities(company.id, dev.id)} >= {
            "list_repositories",
            "create_issue",
        }
        assert {c.name for c in svc.capabilities(company.id, web.id)} >= {
            "search_pages",
            "extract_text",
            "summarize_text",
        }

    def test_cross_company_get_returns_404(self, db: Session) -> None:
        from app.external.integration import IntegrationNotFoundError, IntegrationService

        a, b = _company(db), _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=a.id, provider="email", name="A Email")
        try:
            svc.get(b.id, integration.id)
            raise AssertionError("Foreign-company integration must not be readable")
        except IntegrationNotFoundError:
            pass

    def test_delete(self, db: Session) -> None:
        from app.external.integration import IntegrationNotFoundError, IntegrationService

        company = _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="calendar", name="Cal")
        assert svc.delete(company.id, integration.id) is True
        assert svc.list_(company.id) == []
        try:
            svc.get(company.id, integration.id)
            raise AssertionError("Deleted integration must 404")
        except IntegrationNotFoundError:
            pass


class TestConnections:
    def _setup(self, db: Session) -> tuple[UUID, object]:
        from app.external.integration import IntegrationService

        company = _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        return integration.id, svc

    def test_connect_binds_reference_only_credential(self, db: Session) -> None:
        from app.db.models.external import ConnectionStatus, ExternalCredential
        from app.external.integration import IntegrationService

        company = _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        secret = "mail-secret-9876543210"
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value=secret,
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
            scopes=["email:send"],
            permissions=["email:send"],
        )
        assert connection.status == ConnectionStatus.CONNECTED
        assert connection.credential_reference is not None
        assert connection.credential_reference.startswith("nexref_")

        # No plaintext in the credential row — only a masked suffix.
        cred = db.scalar(
            select(ExternalCredential).where(
                ExternalCredential.reference == connection.credential_reference
            )
        )
        assert cred is not None
        assert secret not in (cred.masked_value or "")
        assert cred.masked_value.endswith("3210")
        assert cred.env_var_hint == "INTEGRATION_EMAIL_API_KEY"

    def test_test_connection_returns_verdict_without_secrets(self, db: Session) -> None:
        from app.external.integration import IntegrationService

        company = _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value="mail-secret-9876543210",
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
        )
        result = svc.test_connection(
            company_id=company.id,
            connection=connection,
            provider_slug="email",
        )
        assert result.result == "connected"
        assert "mail-secret" not in result.message
        assert "mail-secret" not in result.__dict__

    def test_connect_without_credentials_fails_auth_on_test(self, db: Session) -> None:
        from app.db.models.external import ConnectionStatus
        from app.external.integration import IntegrationService

        company = _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
        )
        assert connection.status == ConnectionStatus.CONNECTED
        # No secret in env or one-shot ⇒ auth failure surfaced as a test verdict.
        result = svc.test_connection(
            company_id=company.id, connection=connection, provider_slug="email"
        )
        assert result.result in {"authentication_failed", "authentication_required"}

    def test_revoke_connection(self, db: Session) -> None:
        from app.db.models.external import ConnectionStatus
        from app.external.integration import IntegrationService

        company = _company(db)
        svc = IntegrationService(db)
        integration = svc.create(company_id=company.id, provider="email", name="Email")
        connection = svc.connect(
            company_id=company.id,
            integration_id=integration.id,
            auth_method="api_key",
            secret_value="mail-secret-9876543210",
            env_var_hint="INTEGRATION_EMAIL_API_KEY",
        )
        revoked = svc.revoke(company.id, connection.id)
        assert revoked.status == ConnectionStatus.REVOKED
        assert revoked.revoked_at is not None

    def test_cross_company_connection_is_isolated(self, db: Session) -> None:
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


class TestHttpIntegration:
    """Integration + connection lifecycle over the HTTP API."""

    def _company(self, api_client, db: Session) -> str:
        from app.company.manager import CompanyManager

        global _counter
        _counter += 1
        company = CompanyManager(db).create(name=f"HTTP Integ Co {_counter}", description="http")
        return str(company.id)

    def test_create_connect_list_capabilities_over_http(self, api_client, db: Session) -> None:
        cid = self._company(api_client, db)
        r = api_client.post(
            f"/api/v1/integrations/{cid}", json={"provider": "email", "name": "Email"}
        )
        assert r.status_code == 201, r.text
        iid = r.json()["id"]
        assert r.json()["slug"].startswith("email-")

        r = api_client.get(f"/api/v1/integrations/{cid}/{iid}/capabilities")
        assert r.status_code == 200
        caps = {c["name"] for c in r.json()}
        assert "send_message" in caps and "search_messages" in caps

        r = api_client.post(
            f"/api/v1/integrations/{cid}/{iid}/connections",
            json={
                "auth_method": "api_key",
                "secret_value": "http-mail-secret-1122334455",
                "scopes": ["email:send"],
                "permissions": ["email:send"],
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        conn_id = body["id"]
        # The response must expose only the reference, never the secret.
        assert body["credential_reference"].startswith("nexref_")
        assert "http-mail-secret" not in r.text

        r = api_client.post(
            f"/api/v1/integrations/{cid}/{iid}/connections/{conn_id}/test",
            json={},
        )
        assert r.status_code == 200, r.text
        assert r.json()["result"] == "connected"
        assert "http-mail-secret" not in r.text

        r = api_client.post(
            f"/api/v1/integrations/{cid}/{iid}/connections/{conn_id}/revoke",
            json={},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "revoked"

    def test_foreign_company_cannot_see_integration(self, api_client, db: Session) -> None:
        owner = self._company(api_client, db)
        foreign = self._company(api_client, db)
        r = api_client.post(
            f"/api/v1/integrations/{owner}", json={"provider": "email", "name": "Email"}
        )
        assert r.status_code == 201
        iid = r.json()["id"]
        r = api_client.get(f"/api/v1/integrations/{foreign}/{iid}")
        assert r.status_code == 404
        r = api_client.get(f"/api/v1/integrations/{foreign}/{iid}/capabilities")
        assert r.status_code == 404
