"""Pydantic API schemas for the external integration layer (Phase 10).

Mirror the ORM models in :mod:`app.db.models.external` while staying decoupled
from SQLAlchemy (matching the ``startup.py`` / ``company.py`` convention).
Read schemas serialize the shapes the external services produce; Create/Update
schemas accept the payloads those services consume. Rich JSON payloads
(``input``, ``result``, ``policy``, ``snapshot``, …) are typed as ``Any`` so
the routers can hand back *parsed* objects rather than raw JSON strings.

Credentials are *reference-only*: ``CredentialRefRead`` exposes the opaque
``reference``, ``masked_value``, ``kind``, ``scopes`` and ``env_var_hint`` —
never a secret.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.external import (
    AuthMethod,
    BrowserActionType,
    ComputerActionType,
    ConnectionStatus,
    ConnectionTestResult,
    ContentType,
    CredentialKind,
    DomainDecision,
    ExternalActionStatus,
    ExternalEventSource,
    IntegrationCategory,
    IntegrationStatus,
    Reversibility,
    RiskLevel,
    ScopeType,
    SignatureStatus,
    VerificationStatusExternal,
)


def parse_json(value: str | None) -> Any:
    """Parse a stored JSON text column, returning ``None`` when absent/malformed."""
    if not value:
        return None
    try:
        import json

        return json.loads(value)
    except (ValueError, TypeError):
        return None


# ── Integrations ─────────────────────────────────────────────────────────────


class IntegrationCreate(BaseModel):
    """Create a company-scoped integration instance from a registered provider."""

    provider: str
    name: str = Field(min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=128)
    description: str | None = None
    configuration: dict[str, Any] | None = None
    owner_id: UUID | None = None


class IntegrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    provider: str
    name: str
    slug: str
    description: str | None = None
    category: IntegrationCategory
    auth_type: AuthMethod
    status: IntegrationStatus
    configuration: Any = None
    owner_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None


class CapabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    name: str
    description: str | None = None
    capability_type: str
    risk_level: RiskLevel
    input_schema: Any = None
    output_schema: Any = None
    reversibility: Reversibility
    supports_idempotency: bool
    approval_required: bool
    required_permissions: Any = None
    required_scopes: Any = None


class ConnectionCreate(BaseModel):
    """Connect an integration. Credentials are reference-only: either an
    existing ``credential_reference``, a one-shot ``secret_value`` (used and
    discarded), or an operator ``env_var_hint`` (e.g. ``INTEGRATION_EMAIL_SECRET``)."""

    auth_method: AuthMethod = AuthMethod.API_KEY
    credential_reference: str | None = None
    secret_value: str | None = None
    env_var_hint: str | None = None
    scopes: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class ConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    company_id: UUID
    status: ConnectionStatus
    auth_method: AuthMethod
    credential_reference: str | None = None
    scopes: Any = None
    permissions: Any = None
    metadata: Any = None
    last_used_at: datetime | None = None
    last_tested_at: datetime | None = None
    last_error_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ConnectionTestRead(BaseModel):
    """Result of a connection test. Never includes secrets."""

    result: ConnectionTestResult
    message: str | None = None
    tested_at: str


class CredentialRefRead(BaseModel):
    """Reference-only credential view (§6/§7 — no plaintext)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    integration_id: UUID | None = None
    connection_id: UUID | None = None
    company_id: UUID
    provider: str
    kind: CredentialKind
    masked_value: str
    env_var_hint: str | None = None
    scopes: Any = None
    last_used_at: datetime | None = None
    created_at: datetime


# ── External actions ─────────────────────────────────────────────────────────


class ExternalActionCreate(BaseModel):
    """Create an external action through the governed funnel (§2)."""

    integration_id: UUID
    capability: str
    payload: dict[str, Any] = Field(default_factory=dict)
    action_type: str = "execute"
    connection_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    employee_id: UUID | None = None
    agent_id: UUID | None = None
    approved_gate_id: UUID | None = None
    correlation_id: str | None = Field(default=None, max_length=128)


class ExternalActionAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action_id: UUID
    attempt_number: int
    strategy: str | None = None
    status: str
    retryable: bool
    error_category: str | None = None
    error: str | None = None
    request_id: str | None = None
    external_operation_id: str | None = None
    duration_ms: int | None = None
    created_at: datetime


class ExternalActionRead(BaseModel):
    """Immutable external action journal row with parsed JSON payloads."""

    id: UUID
    company_id: UUID
    integration_id: UUID
    connection_id: UUID | None = None
    employee_id: UUID | None = None
    agent_id: UUID | None = None
    execution_id: UUID | None = None
    workflow_execution_id: UUID | None = None
    orchestration_id: UUID | None = None
    capability: str
    action_type: str
    input: Any = None
    risk_level: RiskLevel
    reversibility: Reversibility
    idempotency_key: str | None = None
    external_operation_id: str | None = None
    policy_result: Any = None
    approval_status: str
    approval_gate_id: UUID | None = None
    status: ExternalActionStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None
    verification: Any = None
    recovery: Any = None
    correlation_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    attempts: list[ExternalActionAttemptRead] = Field(default_factory=list)


# ── External events ──────────────────────────────────────────────────────────


class ExternalEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: ExternalEventSource
    integration_id: UUID | None = None
    company_id: UUID | None = None
    event_type: str
    payload: Any = None
    payload_size: int
    timestamp: datetime | None = None
    verification_status: VerificationStatusExternal
    correlation_id: str | None = None
    signature_status: SignatureStatus
    ingest_id: str | None = None
    received_at: datetime


# ── Browser sessions ─────────────────────────────────────────────────────────


class BrowserSessionCreate(BaseModel):
    allowed_domains: list[str] | None = None
    employee_id: UUID | None = None
    agent_id: UUID | None = None


class BrowserSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    employee_id: UUID | None = None
    agent_id: UUID | None = None
    workflow_execution_id: UUID | None = None
    orchestration_id: UUID | None = None
    status: str
    current_url: str | None = None
    domain: str | None = None
    allowed_domains: Any = None
    policy: Any = None
    metadata: Any = None
    action_count: int
    navigation_count: int
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    terminated_at: datetime | None = None
    created_at: datetime


class BrowserActionCreate(BaseModel):
    action_type: BrowserActionType
    target: dict[str, Any] | None = None
    input: dict[str, Any] | None = None
    approved_gate_id: UUID | None = None


class BrowserActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    company_id: UUID
    action_type: BrowserActionType
    target: Any = None
    input: Any = None
    status: str
    risk_level: RiskLevel
    approval_status: str
    result: Any = None
    error: str | None = None
    duration_ms: int | None = None
    verification: Any = None
    created_at: datetime


class BrowserObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    company_id: UUID
    observation_number: int
    url: str | None = None
    title: str | None = None
    snapshot: Any = None
    screenshot_ref: str | None = None
    content_type: ContentType
    page_state: Any = None
    created_at: datetime


# ── Computer sessions ────────────────────────────────────────────────────────


class ComputerSessionCreate(BaseModel):
    employee_id: UUID | None = None
    agent_id: UUID | None = None


class ComputerSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    employee_id: UUID | None = None
    agent_id: UUID | None = None
    workflow_execution_id: UUID | None = None
    orchestration_id: UUID | None = None
    status: str
    screen: Any = None
    cursor: Any = None
    policy: Any = None
    action_count: int
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    terminated_at: datetime | None = None
    created_at: datetime


class ComputerActionCreate(BaseModel):
    action_type: ComputerActionType
    input: dict[str, Any] | None = None
    approved_gate_id: UUID | None = None


class ComputerActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    company_id: UUID
    action_type: ComputerActionType
    input: Any = None
    status: str
    risk_level: RiskLevel
    approval_status: str
    result: Any = None
    error: str | None = None
    duration_ms: int | None = None
    verification: Any = None
    created_at: datetime


class ComputerObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    company_id: UUID
    observation_number: int
    snapshot: Any = None
    screenshot_ref: str | None = None
    content_type: ContentType
    created_at: datetime


# ── Integration policies & domain rules ──────────────────────────────────────


class IntegrationPolicyCreate(BaseModel):
    integration_id: UUID | None = None
    scope_type: ScopeType = ScopeType.COMPANY
    scope_id: UUID | None = None
    capability_pattern: str | None = None
    risk_level_override: RiskLevel | None = None
    allowed: bool = True
    require_approval: bool = False
    rate_limit: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    allowed_domains: list[str] | None = None
    enabled: bool = True


class IntegrationPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    integration_id: UUID | None = None
    scope_type: ScopeType
    scope_id: UUID | None = None
    capability_pattern: str | None = None
    risk_level_override: RiskLevel | None = None
    allowed: bool
    require_approval: bool
    rate_limit: Any = None
    budget: Any = None
    allowed_domains: Any = None
    enabled: bool
    created_at: datetime
    updated_at: datetime | None = None


class DomainRuleCreate(BaseModel):
    integration_id: UUID | None = None
    scope_type: ScopeType = ScopeType.COMPANY
    scope_id: UUID | None = None
    domain: str
    decision: DomainDecision = DomainDecision.ALLOW
    http_methods: list[str] | None = None
    allowed_paths: list[str] | None = None
    enabled: bool = True


class DomainRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    integration_id: UUID | None = None
    scope_type: ScopeType
    scope_id: UUID | None = None
    domain: str
    decision: DomainDecision
    http_methods: Any = None
    allowed_paths: Any = None
    enabled: bool
    created_at: datetime
    updated_at: datetime | None = None
