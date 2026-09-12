"""External Integrations domain models (Phase 10).

The governed external-interaction layer for NEXUS — integrations (email,
calendar, development platforms, web research), their connections and
capabilities, a *reference-only* credential record, an immutable external
action journal with attempts/verification/recovery traces, normalized external
events (webhook ingest), browser and computer-use sessions/actions/observations
driven through deterministic simulated drivers, and the integration policies +
domain allowlists that determine what a company permits outward.

Design notes (mirroring project convention):
- References (``external_integrations``/``integration_policies``) carry the
  identity/lifecycle/state; rich payloads are stored as JSON Text blobs.
- Enum columns use the project's ``_enum_values`` / ``native_enum=False`` /
  ``create_constraint=False`` convention (VARCHAR storage, no native PG enums).
- Every table is company-scoped (``company_id``) so a connection, action,
  event, browser or computer observation never leaks across companies.
- Credentials are *reference-only*: ``external_credentials`` stores an opaque
  reference, a masked suffix and scopes — never a plaintext secret (§6/§7).
- ``external_actions`` is an immutable journal: once an action reaches a
  terminal status its outcome is preserved with the input, scrubbed result,
  verification trace, and recovery trace.
- The layer is governance-first: capabilities carry risk/reversibility,
  ``integration_policies`` and ``domain_allowlists`` bound what is allowed, and
  high/irreversible actions park behind an ``approval_gates`` row.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.agent import _enum_values
from app.db.session import Base


def _enum_column(enum_cls, name: str):
    """Build a reusable ``Enum`` column using the project's enum convention."""
    return Enum(
        enum_cls,
        name=name,
        values_callable=_enum_values,
        native_enum=False,
        create_constraint=False,
    )


# ── Enums ────────────────────────────────────────────────────────────────────


class IntegrationCategory(StrEnum):
    """Business category of an external integration."""

    COMMUNICATION = "communication"
    PRODUCTIVITY = "productivity"
    DEVELOPMENT = "development"
    STORAGE = "storage"
    DATABASE = "database"
    CRM = "crm"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    FINANCE = "finance"
    WEB = "web"
    BROWSER = "browser"
    COMPUTER = "computer"
    CUSTOM_API = "custom_api"


class IntegrationStatus(StrEnum):
    """Lifecycle status for a company-scoped integration instance."""

    AVAILABLE = "available"
    CONFIGURING = "configuring"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class AuthMethod(StrEnum):
    """How a connection authenticates to the external provider."""

    API_KEY = "api_key"
    BASIC = "basic"
    OAUTH = "oauth"
    NONE = "none"


class ConnectionStatus(StrEnum):
    """Lifecycle status for an integration connection."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ConnectionTestResult(StrEnum):
    """Outcome of a connection test (never includes secrets)."""

    CONNECTED = "connected"
    AUTHENTICATION_FAILED = "authentication_failed"
    PERMISSION_FAILED = "permission_failed"
    RATE_LIMITED = "rate_limited"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INVALID_CONFIGURATION = "invalid_configuration"


class RiskLevel(StrEnum):
    """Risk classification of an external capability or action."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Reversibility(StrEnum):
    """How reversible an external action is."""

    REVERSIBLE = "reversible"
    PARTIALLY_REVERSIBLE = "partially_reversible"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


class CredentialKind(StrEnum):
    """Kind of a stored credential reference."""

    API_KEY = "api_key"
    PASSWORD = "password"
    TOKEN = "token"
    OAUTH = "oauth"
    SECRET = "secret"


class ApprovalStatus(StrEnum):
    """Approval state of an external action."""

    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ExternalActionStatus(StrEnum):
    """Lifecycle status for the external action journal."""

    REQUESTED = "requested"
    AUTHORIZED = "authorized"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ExternalEventSource(StrEnum):
    """Origin of a normalized external event."""

    WEBHOOK = "webhook"
    BROWSER = "browser"
    COMPUTER = "computer"
    INTEGRATION = "integration"
    MANUAL = "manual"


class VerificationStatusExternal(StrEnum):
    """Verification state of an external event."""

    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    NOT_VERIFIED = "not_verified"


class SignatureStatus(StrEnum):
    """Webhook signature verification outcome."""

    VERIFIED = "verified"
    INVALID = "invalid"
    MISSING = "missing"
    NOT_REQUIRED = "not_required"


class BrowserSessionStatus(StrEnum):
    """Lifecycle status for a browser session."""

    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class BrowserActionType(StrEnum):
    """Supported (simulated) browser page actions."""

    OPEN_PAGE = "open_page"
    NAVIGATE = "navigate"
    BACK = "back"
    FORWARD = "forward"
    REFRESH = "refresh"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    SCROLL = "scroll"
    WAIT = "wait"
    EXTRACT_TEXT = "extract_text"
    EXTRACT_LINKS = "extract_links"
    SCREENSHOT = "screenshot"


class ComputerSessionStatus(StrEnum):
    """Lifecycle status for a computer-use session."""

    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class ComputerActionType(StrEnum):
    """Supported (simulated) computer input actions."""

    MOVE_MOUSE = "move_mouse"
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    TYPE = "type"
    KEY_PRESS = "key_press"
    SCROLL = "scroll"
    DRAG = "drag"
    SCREENSHOT = "screenshot"
    WAIT = "wait"


class ContentType(StrEnum):
    """Trust-classification of derived observations (§65 contract).

    External page/computer observations are always EXTERNAL_UNTRUSTED_CONTENT —
    never treated as instructions by the model context builder.
    """

    TRUSTED_SYSTEM = "trusted_system"
    TRUSTED_POLICY = "trusted_policy"
    TRUSTED_USER = "trusted_user"
    EXTERNAL_UNTRUSTED_CONTENT = "external_untrusted_content"
    TOOL_RESULT = "tool_result"


class ScopeType(StrEnum):
    """Scope of an integration policy or domain rule."""

    COMPANY = "company"
    DEPARTMENT = "department"
    EMPLOYEE = "employee"
    INTEGRATION = "integration"


class DomainDecision(StrEnum):
    """Decision for a domain allowlist rule."""

    ALLOW = "allow"
    BLOCK = "block"


# ── External integrations ────────────────────────────────────────────────────


class ExternalIntegration(Base):
    """A company-scoped instance of an external integration."""

    __tablename__ = "external_integrations"
    __table_args__ = (
        UniqueConstraint("company_id", "slug", name="uq_external_integrations_company_slug"),
        Index("ix_external_integrations_company_provider", "company_id", "provider"),
        Index("ix_external_integrations_company_status", "company_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[IntegrationCategory] = mapped_column(
        _enum_column(IntegrationCategory, "integration_category"),
        nullable=False,
        default=IntegrationCategory.CUSTOM_API,
    )
    auth_type: Mapped[AuthMethod] = mapped_column(
        _enum_column(AuthMethod, "integration_auth_type"),
        nullable=False,
        default=AuthMethod.NONE,
    )
    status: Mapped[IntegrationStatus] = mapped_column(
        _enum_column(IntegrationStatus, "integration_status"),
        nullable=False,
        default=IntegrationStatus.AVAILABLE,
    )
    configuration: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IntegrationConnection(Base):
    """A live (or historical) authenticated connection for an integration."""

    __tablename__ = "integration_connections"
    __table_args__ = (
        Index("ix_integration_connections_integration", "integration_id"),
        Index("ix_integration_connections_company_status", "company_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    integration_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("external_integrations.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ConnectionStatus] = mapped_column(
        _enum_column(ConnectionStatus, "connection_status"),
        nullable=False,
        default=ConnectionStatus.CONNECTED,
    )
    auth_method: Mapped[AuthMethod] = mapped_column(
        _enum_column(AuthMethod, "connection_auth_method"),
        nullable=False,
        default=AuthMethod.NONE,
    )
    credential_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    permissions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IntegrationCapability(Base):
    """A capability a provider exposes for an integration instance."""

    __tablename__ = "integration_capabilities"
    __table_args__ = (
        UniqueConstraint("integration_id", "name", name="uq_integration_capabilities_name"),
        Index("ix_integration_capabilities_integration", "integration_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    integration_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("external_integrations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    capability_type: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        _enum_column(RiskLevel, "capability_risk_level"),
        nullable=False,
        default=RiskLevel.LOW,
    )
    input_schema: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    output_schema: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    reversibility: Mapped[Reversibility] = mapped_column(
        _enum_column(Reversibility, "capability_reversibility"),
        nullable=False,
        default=Reversibility.UNKNOWN,
    )
    supports_idempotency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    required_permissions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    required_scopes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExternalCredential(Base):
    """A *reference-only* credential record (Phase 10 §6/§7).

    Never stores a plaintext secret: ``reference`` is an opaque handle the
    CredentialVault resolves at connect time from an operator environment
    variable (or a one-shot request value). Only the masked suffix survives
    for display.
    """

    __tablename__ = "external_credentials"
    __table_args__ = (
        UniqueConstraint("reference", name="uq_external_credentials_reference"),
        Index("ix_external_credentials_company_provider", "company_id", "provider"),
        Index("ix_external_credentials_connection", "connection_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    reference: Mapped[str] = mapped_column(String(128), nullable=False)
    integration_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("external_integrations.id", ondelete="SET NULL"), nullable=True
    )
    connection_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("integration_connections.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[CredentialKind] = mapped_column(
        _enum_column(CredentialKind, "credential_kind"),
        nullable=False,
        default=CredentialKind.API_KEY,
    )
    masked_value: Mapped[str] = mapped_column(String(128), nullable=False)
    env_var_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── External action journal ──────────────────────────────────────────────────


class ExternalAction(Base):
    """Immutrable journal of a governed external action (§2 funnel)."""

    __tablename__ = "external_actions"
    __table_args__ = (
        Index("ix_external_actions_company_status", "company_id", "status"),
        Index("ix_external_actions_company_integration", "company_id", "integration_id"),
        Index(
            "ix_external_actions_idem",
            "company_id",
            "integration_id",
            "capability",
            "idempotency_key",
        ),
        Index("ix_external_actions_gate", "approval_gate_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    integration_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("external_integrations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("integration_connections.id", ondelete="SET NULL"), nullable=True
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    execution_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_executions.id", ondelete="SET NULL"), nullable=True
    )
    workflow_execution_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True
    )
    orchestration_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("orchestrations.id", ondelete="SET NULL"), nullable=True
    )
    capability: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    input: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    risk_level: Mapped[RiskLevel] = mapped_column(
        _enum_column(RiskLevel, "action_risk_level"),
        nullable=False,
        default=RiskLevel.LOW,
    )
    reversibility: Mapped[Reversibility] = mapped_column(
        _enum_column(Reversibility, "action_reversibility"),
        nullable=False,
        default=Reversibility.UNKNOWN,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_operation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    policy_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        _enum_column(ApprovalStatus, "action_approval_status"),
        nullable=False,
        default=ApprovalStatus.NOT_REQUIRED,
    )
    approval_gate_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_gates.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ExternalActionStatus] = mapped_column(
        _enum_column(ExternalActionStatus, "external_action_status"),
        nullable=False,
        default=ExternalActionStatus.REQUESTED,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON (scrubbed)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    recovery: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExternalActionAttempt(Base):
    """A single execution attempt for an external action (recovery trace)."""

    __tablename__ = "external_action_attempts"
    __table_args__ = (
        UniqueConstraint("action_id", "attempt_number", name="uq_external_attempts_number"),
        Index("ix_external_action_attempts_action", "action_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    action_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("external_actions.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    strategy: Mapped[str] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="executing")
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_operation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── External events / webhook ingest ─────────────────────────────────────────


class ExternalEvent(Base):
    """Normalized external event (webhook/other) — never a trusted command."""

    __tablename__ = "external_events"
    __table_args__ = (
        UniqueConstraint("source", "ingest_id", name="uq_external_events_ingest"),
        Index("ix_external_events_company_received", "company_id", "received_at"),
        Index("ix_external_events_source_type", "source", "event_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source: Mapped[ExternalEventSource] = mapped_column(
        _enum_column(ExternalEventSource, "external_event_source"),
        nullable=False,
        default=ExternalEventSource.INTEGRATION,
    )
    integration_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("external_integrations.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    payload_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[VerificationStatusExternal] = mapped_column(
        _enum_column(VerificationStatusExternal, "external_event_verification"),
        nullable=False,
        default=VerificationStatusExternal.NOT_VERIFIED,
    )
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signature_status: Mapped[SignatureStatus] = mapped_column(
        _enum_column(SignatureStatus, "external_event_signature"),
        nullable=False,
        default=SignatureStatus.NOT_REQUIRED,
    )
    ingest_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Browser-use ──────────────────────────────────────────────────────────────


class BrowserSession(Base):
    """A bounded browser-use session driven through the simulated driver."""

    __tablename__ = "browser_sessions"
    __table_args__ = (
        Index("ix_browser_sessions_company_status", "company_id", "status"),
        Index("ix_browser_sessions_owner", "employee_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    workflow_execution_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True
    )
    orchestration_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("orchestrations.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[BrowserSessionStatus] = mapped_column(
        _enum_column(BrowserSessionStatus, "browser_session_status"),
        nullable=False,
        default=BrowserSessionStatus.CREATED,
    )
    current_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    allowed_domains: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    policy: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    action_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    navigation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BrowserAction(Base):
    """A single (simulated) browser action within a session."""

    __tablename__ = "browser_actions"
    __table_args__ = (
        Index("ix_browser_actions_session_created", "session_id", "created_at"),
        Index("ix_browser_actions_company_created", "company_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("browser_sessions.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[BrowserActionType] = mapped_column(
        _enum_column(BrowserActionType, "browser_action_type"),
        nullable=False,
    )
    target: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    input: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    risk_level: Mapped[RiskLevel] = mapped_column(
        _enum_column(RiskLevel, "browser_action_risk_level"),
        nullable=False,
        default=RiskLevel.LOW,
    )
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        _enum_column(ApprovalStatus, "browser_action_approval"),
        nullable=False,
        default=ApprovalStatus.NOT_REQUIRED,
    )
    result: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BrowserObservation(Base):
    """A size-limited, untrusted page observation captured by the session."""

    __tablename__ = "browser_observations"
    __table_args__ = (
        UniqueConstraint("session_id", "observation_number", name="uq_browser_observations_number"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("browser_sessions.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    observation_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON (size-limited)
    screenshot_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_type: Mapped[ContentType] = mapped_column(
        _enum_column(ContentType, "observation_content_type"),
        nullable=False,
        default=ContentType.EXTERNAL_UNTRUSTED_CONTENT,
    )
    page_state: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Computer-use ─────────────────────────────────────────────────────────────


class ComputerSession(Base):
    """A bounded computer-use session driven through the simulated driver."""

    __tablename__ = "computer_sessions"
    __table_args__ = (
        Index("ix_computer_sessions_company_status", "company_id", "status"),
        Index("ix_computer_sessions_owner", "employee_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    workflow_execution_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True
    )
    orchestration_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("orchestrations.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ComputerSessionStatus] = mapped_column(
        _enum_column(ComputerSessionStatus, "computer_session_status"),
        nullable=False,
        default=ComputerSessionStatus.CREATED,
    )
    screen: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    policy: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    action_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ComputerAction(Base):
    """A single simulated computer-input action within a session."""

    __tablename__ = "computer_actions"
    __table_args__ = (
        Index("ix_computer_actions_session_created", "session_id", "created_at"),
        Index("ix_computer_actions_company_created", "company_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("computer_sessions.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[ComputerActionType] = mapped_column(
        _enum_column(ComputerActionType, "computer_action_type"),
        nullable=False,
    )
    input: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    risk_level: Mapped[RiskLevel] = mapped_column(
        _enum_column(RiskLevel, "computer_action_risk_level"),
        nullable=False,
        default=RiskLevel.LOW,
    )
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        _enum_column(ApprovalStatus, "computer_action_approval"),
        nullable=False,
        default=ApprovalStatus.NOT_REQUIRED,
    )
    result: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ComputerObservation(Base):
    """A structured screen observation (never sensitive desktop content)."""

    __tablename__ = "computer_observations"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "observation_number", name="uq_computer_observations_number"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("computer_sessions.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    observation_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON (size-limited)
    screenshot_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_type: Mapped[ContentType] = mapped_column(
        _enum_column(ContentType, "computer_observation_content_type"),
        nullable=False,
        default=ContentType.EXTERNAL_UNTRUSTED_CONTENT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Integration policies & domain allowlists ─────────────────────────────────


class IntegrationPolicy(Base):
    """A company-level external action policy (most-restrictive-wins)."""

    __tablename__ = "integration_policies"
    __table_args__ = (
        Index("ix_integration_policies_company_integration", "company_id", "integration_id"),
        Index(
            "ix_integration_policies_scope",
            "company_id",
            "scope_type",
            "scope_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    integration_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("external_integrations.id", ondelete="SET NULL"), nullable=True
    )
    scope_type: Mapped[ScopeType] = mapped_column(
        _enum_column(ScopeType, "integration_policy_scope_type"),
        nullable=False,
        default=ScopeType.COMPANY,
    )
    scope_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    capability_pattern: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_level_override: Mapped[RiskLevel | None] = mapped_column(
        _enum_column(RiskLevel, "integration_policy_risk_override"), nullable=True
    )
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    require_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rate_limit: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    budget: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    allowed_domains: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DomainAllowlist(Base):
    """A domain rule governing outbound navigation/HTTP for a company."""

    __tablename__ = "domain_allowlists"
    __table_args__ = (
        Index("ix_domain_allowlists_company_domain", "company_id", "domain"),
        Index("ix_domain_allowlists_company_scope", "company_id", "scope_type", "scope_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    integration_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("external_integrations.id", ondelete="SET NULL"), nullable=True
    )
    scope_type: Mapped[ScopeType] = mapped_column(
        _enum_column(ScopeType, "domain_rule_scope_type"),
        nullable=False,
        default=ScopeType.COMPANY,
    )
    scope_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[DomainDecision] = mapped_column(
        _enum_column(DomainDecision, "domain_rule_decision"),
        nullable=False,
        default=DomainDecision.ALLOW,
    )
    http_methods: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    allowed_paths: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
