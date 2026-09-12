"""Integration service — lifecycle of company-scoped integrations (Phase 10).

``IntegrationService`` mirrors the Phase 0–9 ``Service(db)`` convention: thin
DB-facing methods with real commits and shared audit events. It creates
provider-backed integration instances, materializes each provider capability as
an ``integration_capabilities`` row, manages connections (with *reference-only*
credential binding), tests connections through the provider, and revokes them.
No secret ever appears in a response — credentials are masked references only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.db.models.external import (
    AuthMethod,
    ConnectionStatus,
    CredentialKind,
    ExternalCredential,
    ExternalIntegration,
    IntegrationCapability,
    IntegrationConnection,
    IntegrationStatus,
)
from app.external.api.auth import resolve_auth_context
from app.external.credential import CredentialVault
from app.external.events import ExternalEventLogger, ExternalEvents
from app.external.registry import get_provider
from app.external.types import (
    ConnectionTest,
    ExternalAuthFailure,
    ExternalValidationFailure,
)


class IntegrationNotFoundError(ValueError):
    def __init__(self, integration_id: UUID) -> None:
        super().__init__(f"Integration {integration_id} not found")
        self.integration_id = integration_id


class IntegrationService:
    """Company-scoped integration + connection lifecycle."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = ExternalEventLogger(db)
        self._vault = CredentialVault(db)

    # ── Integrations ──────────────────────────────────────────────────

    def create(
        self,
        *,
        company_id: UUID,
        provider: str,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        configuration: dict[str, Any] | None = None,
        owner_id: UUID | None = None,
    ) -> ExternalIntegration:
        """Create an integration instance from a registered provider."""
        adapter = get_provider(provider)  # raises KeyError on unknown provider
        integration = ExternalIntegration(
            company_id=company_id,
            provider=provider,
            name=name,
            slug=slug or f"{provider}-{company_id.hex[:6]}",
            description=description or adapter.name,
            category=adapter.category,
            auth_type=adapter.auth_type,
            status=IntegrationStatus.AVAILABLE,
            configuration=json.dumps(configuration or {}),
            owner_id=owner_id,
        )
        self._db.add(integration)
        self._db.flush()
        self._materialize_capabilities(integration, adapter.capabilities())
        self._db.commit()
        self._db.refresh(integration)
        self._events.log(
            action=ExternalEvents.INTEGRATION_CREATED,
            company_id=company_id,
            actor="system",
            target_type="integration",
            target_id=integration.id,
            details={"provider": provider, "category": adapter.category.value},
        )
        return integration

    def _materialize_capabilities(self, integration: ExternalIntegration, caps: list[Any]) -> None:
        for cap in caps:
            self._db.add(
                IntegrationCapability(
                    integration_id=integration.id,
                    name=cap.name,
                    description=cap.description,
                    capability_type=cap.capability_type,
                    risk_level=cap.risk_level,
                    input_schema=json.dumps(cap.input_schema) if cap.input_schema else None,
                    output_schema=json.dumps(cap.output_schema) if cap.output_schema else None,
                    reversibility=cap.reversibility,
                    supports_idempotency=cap.supports_idempotency,
                    approval_required=cap.approval_required,
                    required_permissions=json.dumps(cap.required_permissions),
                    required_scopes=json.dumps(cap.required_scopes),
                )
            )

    def get(self, company_id: UUID, integration_id: UUID) -> ExternalIntegration:
        integration = self._db.get(ExternalIntegration, integration_id)
        if integration is None or integration.company_id != company_id:
            raise IntegrationNotFoundError(integration_id)
        return integration

    def list_(self, company_id: UUID) -> list[ExternalIntegration]:
        return list(
            self._db.execute(
                sa_select(ExternalIntegration)
                .where(ExternalIntegration.company_id == company_id)
                .order_by(ExternalIntegration.created_at.desc())
            )
            .scalars()
            .all()
        )

    def capabilities(self, company_id: UUID, integration_id: UUID) -> list[IntegrationCapability]:
        integration = self.get(company_id, integration_id)
        return list(
            self._db.execute(
                sa_select(IntegrationCapability)
                .where(IntegrationCapability.integration_id == integration.id)
                .order_by(IntegrationCapability.name.asc())
            )
            .scalars()
            .all()
        )

    def capability(
        self, company_id: UUID, integration_id: UUID, name: str
    ) -> IntegrationCapability:
        """Return the capability row for a named capability (404 on mismatch)."""
        integration = self.get(company_id, integration_id)
        row = self._db.scalar(
            sa_select(IntegrationCapability).where(
                IntegrationCapability.integration_id == integration.id,
                IntegrationCapability.name == name,
            )
        )
        if row is None:
            raise ExternalValidationFailure(f"Capability {name!r} not found on integration")
        return row

    def update_status(
        self, company_id: UUID, integration_id: UUID, status: IntegrationStatus
    ) -> ExternalIntegration:
        integration = self.get(company_id, integration_id)
        integration.status = IntegrationStatus(status)
        self._db.commit()
        self._events.log(
            action=ExternalEvents.INTEGRATION_UPDATED,
            company_id=company_id,
            target_type="integration",
            target_id=integration_id,
            details={"status": integration.status.value},
        )
        return integration

    def delete(self, company_id: UUID, integration_id: UUID) -> bool:
        integration = self.get(company_id, integration_id)
        self._db.delete(integration)
        self._db.commit()
        self._events.log(
            action=ExternalEvents.INTEGRATION_DELETED,
            company_id=company_id,
            target_type="integration",
            target_id=integration_id,
        )
        return True

    # ── Connections ───────────────────────────────────────────────────

    def connect(
        self,
        *,
        company_id: UUID,
        integration_id: UUID,
        auth_method: AuthMethod | str,
        credential_reference: str | None = None,
        secret_value: str | None = None,
        env_var_hint: str | None = None,
        scopes: list[str] | None = None,
        permissions: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IntegrationConnection:
        """Create a connection, binding a *reference-only* credential."""
        integration = self.get(company_id, integration_id)
        auth = AuthMethod(auth_method)
        reference = credential_reference
        if auth is not AuthMethod.NONE and not reference:
            kind = _kind_for_auth(auth)
            credential = self._vault.create_reference(
                company_id=company_id,
                provider=integration.provider,
                kind=kind,
                secret_value=secret_value,
                env_var_hint=env_var_hint,
                scopes=scopes,
                integration_id=integration_id,
            )
            reference = credential.reference

        connection = IntegrationConnection(
            integration_id=integration.id,
            company_id=company_id,
            status=ConnectionStatus.CONNECTED,
            auth_method=auth,
            credential_reference=reference,
            scopes=json.dumps(scopes or []),
            permissions=json.dumps(permissions or []),
            metadata_json=json.dumps(metadata or {}),
        )
        self._db.add(connection)
        self._db.flush()
        if reference:
            self._vault.get(company_id, reference)
            self._bind_credential(company_id, integration_id, reference, connection.id)
        integration.status = IntegrationStatus.CONNECTED
        self._db.commit()
        self._db.refresh(connection)
        self._events.log(
            action=ExternalEvents.CONNECTION_CREATED,
            company_id=company_id,
            target_type="connection",
            target_id=connection.id,
            details={
                "integration": integration.provider,
                "auth": auth.value,
                "credential": "reference",
            },
        )
        return connection

    def _bind_credential(
        self, company_id: UUID, integration_id: UUID, reference: str, connection_id: UUID
    ) -> None:
        """Point an existing credential reference's connection_id at the new connection."""
        from sqlalchemy import update

        self._db.execute(
            update(ExternalCredential)
            .where(
                ExternalCredential.reference == reference,
                ExternalCredential.company_id == company_id,
            )
            .values(connection_id=connection_id)
        )

    def list_connections(
        self, company_id: UUID, integration_id: UUID
    ) -> list[IntegrationConnection]:
        integration = self.get(company_id, integration_id)
        return list(
            self._db.execute(
                sa_select(IntegrationConnection)
                .where(
                    IntegrationConnection.integration_id == integration.id,
                    IntegrationConnection.company_id == company_id,
                )
                .order_by(IntegrationConnection.created_at.desc())
            )
            .scalars()
            .all()
        )

    def get_connection(self, company_id: UUID, connection_id: UUID) -> IntegrationConnection:
        connection = self._db.get(IntegrationConnection, connection_id)
        if connection is None or connection.company_id != company_id:
            raise ExternalValidationFailure(f"Connection {connection_id} not found")
        return connection

    def test_connection(
        self,
        *,
        company_id: UUID,
        connection: IntegrationConnection,
        provider_slug: str,
    ) -> ConnectionTest:
        """Test a connection through the provider (result carries no secrets)."""
        try:
            auth = resolve_auth_context(
                self._db,
                company_id=company_id,
                provider=provider_slug,
                connection=connection,
                credential_reference=connection.credential_reference,
            )
            result, message = get_provider(provider_slug).test(
                payload={}, auth=auth, context={"company_id": str(company_id)}
            )
            tested_at = datetime.now(UTC).isoformat()
            connection.last_tested_at = datetime.now(UTC)
            self._db.commit()
            self._events.log(
                action=ExternalEvents.CONNECTION_TESTED,
                company_id=company_id,
                target_type="connection",
                target_id=connection.id,
                details={"result": result},
            )
            return ConnectionTest(result=result, message=message, tested_at=tested_at)
        except ExternalAuthFailure as exc:
            connection.last_error_at = datetime.now(UTC)
            self._db.commit()
            return ConnectionTest(
                result="authentication_failed",
                message=str(exc)[:512],
                tested_at=datetime.now(UTC).isoformat(),
            )

    def revoke(self, company_id: UUID, connection_id: UUID) -> IntegrationConnection:
        connection = self.get_connection(company_id, connection_id)
        connection.status = ConnectionStatus.REVOKED
        connection.revoked_at = datetime.now(UTC)
        self._db.commit()
        self._events.log(
            action=ExternalEvents.CONNECTION_REVOKED,
            company_id=company_id,
            target_type="connection",
            target_id=connection_id,
        )
        return connection

    def resolve_provider(self, integration: ExternalIntegration) -> str:
        return integration.provider


def _kind_for_auth(auth: AuthMethod) -> CredentialKind:
    return {
        AuthMethod.API_KEY: CredentialKind.API_KEY,
        AuthMethod.BASIC: CredentialKind.PASSWORD,
        AuthMethod.OAUTH: CredentialKind.OAUTH,
        AuthMethod.NONE: CredentialKind.SECRET,
    }[auth]
