"""External integration management endpoints (Phase 10 §47/§48).

Company-scoped CRUD for integration instances, capability discovery, and the
connection lifecycle (connect / test / revoke). Credentials are reference-only
— ``secret_value`` is used once and discarded, never persisted. Integration
policies and domain-allowlist rules (the tables that bound what a company
permits outward) are exposed here too — the policy resolver consumes them.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.models.external import (
    DomainAllowlist,
    IntegrationConnection,
    IntegrationPolicy,
)
from app.db.session import get_db
from app.external.integration import IntegrationNotFoundError, IntegrationService
from app.external.result import ExternalActionError
from app.schemas.external import (
    CapabilityRead,
    ConnectionCreate,
    ConnectionRead,
    ConnectionTestRead,
    DomainRuleCreate,
    DomainRuleRead,
    IntegrationCreate,
    IntegrationPolicyCreate,
    IntegrationPolicyRead,
    IntegrationRead,
)

router = APIRouter(tags=["external-integrations"], prefix="/integrations")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


# ── Integration instances ────────────────────────────────────────────────


@router.post(
    "/{company_id}",
    response_model=IntegrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an integration instance from a registered provider",
)
def create_integration(
    company_id: UUID,
    payload: IntegrationCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> IntegrationRead:
    _company_or_404(db, company_id)
    try:
        integration = IntegrationService(db).create(
            company_id=company_id,
            provider=payload.provider,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            configuration=payload.configuration,
            owner_id=payload.owner_id,
        )
        integration.configuration = (
            json.loads(integration.configuration) if integration.configuration else None
        )
        return integration
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as e:  # noqa: BLE001 - validation errors surface as 400
        raise _error(e) from e


@router.get(
    "/{company_id}",
    response_model=list[IntegrationRead],
    summary="List integrations for a company",
)
def list_integrations(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[IntegrationRead]:
    _company_or_404(db, company_id)
    rows = IntegrationService(db).list_(company_id)
    for row in rows:
        row.configuration = json.loads(row.configuration) if row.configuration else None
    return rows


@router.get(
    "/{company_id}/{integration_id}",
    response_model=IntegrationRead,
    summary="Get one integration (404 isolated per company)",
)
def get_integration(
    company_id: UUID,
    integration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> IntegrationRead:
    _company_or_404(db, company_id)
    try:
        integration = IntegrationService(db).get(company_id, integration_id)
        integration.configuration = (
            json.loads(integration.configuration) if integration.configuration else None
        )
        return integration
    except IntegrationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/{company_id}/{integration_id}", summary="Delete an integration (cascades connections)"
)
def delete_integration(
    company_id: UUID,
    integration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    _company_or_404(db, company_id)
    try:
        IntegrationService(db).delete(company_id, integration_id)
    except IntegrationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "integration_id": str(integration_id)}


# ── Capabilities ──────────────────────────────────────────────────────────


@router.get(
    "/{company_id}/{integration_id}/capabilities",
    response_model=list[CapabilityRead],
    summary="List provider capabilities materialized for an integration",
)
def list_capabilities(
    company_id: UUID,
    integration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[CapabilityRead]:
    _company_or_404(db, company_id)
    svc = IntegrationService(db)
    try:
        rows = svc.capabilities(company_id, integration_id)
    except IntegrationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    for row in rows:
        row.input_schema = json.loads(row.input_schema) if row.input_schema else None
        row.output_schema = json.loads(row.output_schema) if row.output_schema else None
        row.required_permissions = (
            json.loads(row.required_permissions) if row.required_permissions else None
        )
        row.required_scopes = json.loads(row.required_scopes) if row.required_scopes else None
    return rows


# ── Connections ────────────────────────────────────────────────────────────


def _connection_to_read(connection: IntegrationConnection) -> ConnectionRead:
    """Serialize a connection with JSON columns parsed — without mutating the
    attached ORM row (mutating triggers an autoflush of the parsed lists back
    into the VARCHAR columns during response serialization)."""
    return ConnectionRead(
        id=connection.id,
        integration_id=connection.integration_id,
        company_id=connection.company_id,
        status=connection.status,
        auth_method=connection.auth_method,
        credential_reference=connection.credential_reference,
        scopes=json.loads(connection.scopes) if connection.scopes else None,
        permissions=json.loads(connection.permissions) if connection.permissions else None,
        metadata=json.loads(connection.metadata_json) if connection.metadata_json else None,
        last_used_at=connection.last_used_at,
        last_tested_at=connection.last_tested_at,
        last_error_at=connection.last_error_at,
        revoked_at=connection.revoked_at,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.post(
    "/{company_id}/{integration_id}/connections",
    response_model=ConnectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Connect an integration with a reference-only credential",
)
def connect_integration(
    company_id: UUID,
    integration_id: UUID,
    payload: ConnectionCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ConnectionRead:
    _company_or_404(db, company_id)
    try:
        connection = IntegrationService(db).connect(
            company_id=company_id,
            integration_id=integration_id,
            auth_method=payload.auth_method,
            credential_reference=payload.credential_reference,
            secret_value=payload.secret_value,
            env_var_hint=payload.env_var_hint,
            scopes=payload.scopes,
            permissions=payload.permissions,
            metadata=payload.metadata,
        )
        return _connection_to_read(connection)
    except (IntegrationNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=404 if isinstance(exc, IntegrationNotFoundError) else 400, detail=str(exc)
        ) from exc


@router.get(
    "/{company_id}/{integration_id}/connections",
    response_model=list[ConnectionRead],
    summary="List connections for an integration",
)
def list_connections(
    company_id: UUID,
    integration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ConnectionRead]:
    _company_or_404(db, company_id)
    try:
        rows = IntegrationService(db).list_connections(company_id, integration_id)
    except IntegrationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_connection_to_read(row) for row in rows]


@router.get(
    "/{company_id}/{integration_id}/connections/{connection_id}",
    response_model=ConnectionRead,
    summary="Get one connection",
)
def get_connection(
    company_id: UUID,
    integration_id: UUID,
    connection_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ConnectionRead:
    _company_or_404(db, company_id)
    svc = IntegrationService(db)
    try:
        svc.get(company_id, integration_id)
        connection = svc.get_connection(company_id, connection_id)
    except (IntegrationNotFoundError, ExternalActionError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _connection_to_read(connection)


@router.post(
    "/{company_id}/{integration_id}/connections/{connection_id}/test",
    response_model=ConnectionTestRead,
    summary="Test a connection through its provider (never exposes secrets)",
)
def test_connection(
    company_id: UUID,
    integration_id: UUID,
    connection_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ConnectionTestRead:
    _company_or_404(db, company_id)
    svc = IntegrationService(db)
    try:
        integration = svc.get(company_id, integration_id)
        connection = svc.get_connection(company_id, connection_id)
    except (IntegrationNotFoundError, ExternalActionError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = svc.test_connection(
        company_id=company_id,
        connection=connection,
        provider_slug=integration.provider,
    )
    return ConnectionTestRead(
        result=result.result, message=result.message, tested_at=result.tested_at
    )


@router.post(
    "/{company_id}/{integration_id}/connections/{connection_id}/revoke",
    response_model=ConnectionRead,
    summary="Revoke a connection (irreversible)",
)
def revoke_connection(
    company_id: UUID,
    integration_id: UUID,
    connection_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ConnectionRead:
    _company_or_404(db, company_id)
    svc = IntegrationService(db)
    try:
        svc.get(company_id, integration_id)
        connection = svc.revoke(company_id, connection_id)
    except (IntegrationNotFoundError, ExternalActionError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _connection_to_read(connection)


# ── Integration policies & domain allowlists ──────────────────────────────


def _policy_to_read(row: IntegrationPolicy) -> dict[str, Any]:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "integration_id": row.integration_id,
        "scope_type": row.scope_type.value if row.scope_type else None,
        "scope_id": row.scope_id,
        "capability_pattern": row.capability_pattern,
        "risk_level_override": row.risk_level_override.value if row.risk_level_override else None,
        "allowed": row.allowed,
        "require_approval": row.require_approval,
        "rate_limit": json.loads(row.rate_limit) if row.rate_limit else None,
        "budget": json.loads(row.budget) if row.budget else None,
        "allowed_domains": json.loads(row.allowed_domains) if row.allowed_domains else None,
        "enabled": row.enabled,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get(
    "/{company_id}/policies",
    response_model=list[IntegrationPolicyRead],
    summary="List integration policies",
)
def list_policies(company_id: UUID, db: Session = Depends(get_db)) -> list[IntegrationPolicyRead]:  # noqa: B008
    _company_or_404(db, company_id)
    rows = (
        db.execute(
            sa_select(IntegrationPolicy)
            .where(IntegrationPolicy.company_id == company_id)
            .order_by(IntegrationPolicy.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [_policy_to_read(r) for r in rows]


@router.post(
    "/{company_id}/policies",
    response_model=IntegrationPolicyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an integration policy rule",
)
def create_policy(
    company_id: UUID,
    payload: IntegrationPolicyCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> IntegrationPolicyRead:
    _company_or_404(db, company_id)
    row = IntegrationPolicy(
        company_id=company_id,
        integration_id=payload.integration_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        capability_pattern=payload.capability_pattern,
        risk_level_override=payload.risk_level_override,
        allowed=payload.allowed,
        require_approval=payload.require_approval,
        rate_limit=json.dumps(payload.rate_limit or {}),
        budget=json.dumps(payload.budget or {}),
        allowed_domains=json.dumps(payload.allowed_domains or []),
        enabled=payload.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _policy_to_read(row)


def _domain_to_read(row: DomainAllowlist) -> dict[str, Any]:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "integration_id": row.integration_id,
        "scope_type": row.scope_type.value if row.scope_type else None,
        "scope_id": row.scope_id,
        "domain": row.domain,
        "decision": row.decision.value if row.decision else None,
        "http_methods": json.loads(row.http_methods) if row.http_methods else None,
        "allowed_paths": json.loads(row.allowed_paths) if row.allowed_paths else None,
        "enabled": row.enabled,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get(
    "/{company_id}/domains",
    response_model=list[DomainRuleRead],
    summary="List domain allowlist rules",
)
def list_domain_rules(company_id: UUID, db: Session = Depends(get_db)) -> list[DomainRuleRead]:  # noqa: B008
    _company_or_404(db, company_id)
    rows = (
        db.execute(
            sa_select(DomainAllowlist)
            .where(DomainAllowlist.company_id == company_id)
            .order_by(DomainAllowlist.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [_domain_to_read(r) for r in rows]


@router.post(
    "/{company_id}/domains",
    response_model=DomainRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a domain allowlist rule",
)
def create_domain_rule(
    company_id: UUID,
    payload: DomainRuleCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> DomainRuleRead:
    _company_or_404(db, company_id)
    row = DomainAllowlist(
        company_id=company_id,
        integration_id=payload.integration_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        domain=payload.domain,
        decision=payload.decision,
        http_methods=json.dumps(payload.http_methods or []),
        allowed_paths=json.dumps(payload.allowed_paths or []),
        enabled=payload.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _domain_to_read(row)


# ── Policy evaluation (observability) ──────────────────────────────────────


@router.get(
    "/{company_id}/policy/evaluate", summary="Resolve the effective policy for one capability call"
)
def evaluate_policy(
    company_id: UUID,
    integration_id: UUID = Query(...),  # noqa: B008
    capability: str = Query(...),  # noqa: B008
    risk_level: str = Query(default="low"),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    from app.db.models.external import RiskLevel
    from app.external.policy import ExternalPolicyResolver

    _company_or_404(db, company_id)
    svc = IntegrationService(db)
    try:
        integration = svc.get(company_id, integration_id)
        capability_row = svc.capability(company_id, integration_id, capability)
    except (IntegrationNotFoundError, ExternalActionError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    resolution = ExternalPolicyResolver(db).resolve(
        company_id=company_id,
        integration_id=integration_id,
        capability_name=capability,
        risk_level=RiskLevel(risk_level),
        payload=None,
        capability_row=capability_row,
        default_rate_limit=None,
    )
    data = resolution.to_dict()
    data["integration"] = integration.provider
    data["capability"] = capability
    return data
