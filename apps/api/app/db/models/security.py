"""Security, Governance & Production Hardening domain models (Phase 11).

The identity → authorization → policy → resources → approval → action →
verification → audit → observability → recovery chain (§FINAL OBJECTIVE).
This module adds the security subsystem as *enforcement on top of* Phases
0–10 — every table here is additive, and existing runtime only observes the
governing layers through the new services (never through duplication).

Design notes (mirroring project convention):
- References carry identity/lifecycle/state; rich payloads are JSON Text.
- Enum columns use the project's ``_enum_values`` / ``native_enum=False`` /
  ``create_constraint=False`` convention (VARCHAR storage, no native enums).
- Company-scoped tables carry ``company_id`` (+ index) so governance never
  leaks across companies.
- Secrets/credentials are stored as ciphertext or references — never plaintext.
  ``secrets`` holds a ciphertext blob keyed by ``encryption_key`` id.
- ``audit_events`` is append-only and hash-chained (``prev_hash``/``hash``):
  no service UPDATE/DELETE path exists; integrity is verifiable any time.
- ``system_flags`` are the kill switch; ``governance_controls`` mirrors them
  as a human-readable registry of each enforcement rule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
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


class IdentityKind(StrEnum):
    """Kind of principal that can hold a token / be held accountable."""

    USER = "user"
    SERVICE = "service"
    AI_EMPLOYEE = "ai_employee"
    AGENT = "agent"
    COMPANY = "company"


class IdentityStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    DISABLED = "disabled"


class UserStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"
    LOCKED = "locked"
    DISABLED = "disabled"


class AuthSessionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REPLACED = "replaced"


class RoleScope(StrEnum):
    SYSTEM = "system"
    COMPANY = "company"


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PolicyScope(StrEnum):
    SYSTEM = "system"
    COMPANY = "company"
    DEPARTMENT = "department"
    EMPLOYEE = "employee"
    AGENT = "agent"
    EXTERNAL = "external"


class PolicyDecisionType(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class SecretKind(StrEnum):
    OPERATOR = "operator"
    INTEGRATION = "integration"
    API_KEY = "api_key"
    PASSWORD = "password"
    ENCRYPTION = "encryption"


class SecretStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    REVOKED = "revoked"
    PENDING_ROTATION = "pending_rotation"


class EncryptionKeyStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    COMPROMISED = "compromised"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    PENDING = "pending"
    REQUIRE_APPROVAL = "require_approval"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEventCategory(StrEnum):
    """Thirteen security event categories (§48)."""

    AUTH_FAILURE = "auth_failure"
    TOKEN_INVALID = "token_invalid"
    PERMISSION_DENIED = "permission_denied"
    POLICY_DENIED = "policy_denied"
    CROSS_COMPANY_ACCESS = "cross_company_access"
    PROMPT_INJECTION = "prompt_injection"
    SSRF_BLOCKED = "ssrf_blocked"
    EXTERNAL_ACTION_SUSPICIOUS = "external_action_suspicious"
    RESOURCE_EXCEEDED = "resource_exceeded"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SECRET_ACCESS_DENIED = "secret_access_denied"
    DATA_EXFILTRATION_BLOCKED = "data_exfiltration_blocked"
    SCANNER_SUSPECTED = "scanner_suspected"


class SecurityAlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class IncidentStatus(StrEnum):
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentActionState(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    REVERTED = "reverted"


class SystemFlagScope(StrEnum):
    GLOBAL = "global"
    COMPANY = "company"
    EMPLOYEE = "employee"
    AGENT = "agent"
    EXTERNAL = "external"
    WORKFLOW = "workflow"


class SystemFlagStatus(StrEnum):
    ACTIVE = "active"
    CLEARED = "cleared"


class BreakGlassStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ResourceCategory(StrEnum):
    TOKENS = "tokens"
    COST = "cost"
    TOOL_CALLS = "tool_calls"
    ITERATIONS = "iterations"
    DURATION_SECONDS = "duration_seconds"
    MEMORY = "memory"


class ResourceLimitScope(StrEnum):
    GLOBAL = "global"
    COMPANY = "company"
    EMPLOYEE = "employee"
    AGENT = "agent"


class FeatureFlagScope(StrEnum):
    GLOBAL = "global"
    COMPANY = "company"


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    SECRET = "secret"


class RetentionEntityType(StrEnum):
    EXECUTIONS = "executions"
    LOGS = "logs"
    AUDIT_EVENTS = "audit_events"
    SECURITY_EVENTS = "security_events"
    MEMORY = "memory"
    OBSERVATIONS = "observations"
    TOOL_CALLS = "tool_calls"
    SCREENSHOTS = "screenshots"


class DeletionSemantics(StrEnum):
    HARD = "hard"
    SOFT = "soft"
    ANONYMIZE = "anonymize"
    RETENTION_LOCK = "retention_lock"


class DeadLetterStatus(StrEnum):
    PENDING = "pending"
    RETRIED = "retried"
    DEAD = "dead"
    DISCARDED = "discarded"


class IdempotencyOutcome(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILURE = "failure"


class ContextAuthority(StrEnum):
    """Trust authority values — deliberately the Phase 10 context-vocabulary so
    both systems speak the same labels (``context_authorities`` stores these)."""

    TRUSTED_SYSTEM = "trusted_system"
    TRUSTED_POLICY = "trusted_policy"
    TRUSTED_USER = "trusted_user"
    TOOL_RESULT = "tool_result"
    EXTERNAL_UNTRUSTED_CONTENT = "external_untrusted_content"
    SYSTEMS = "systems"  # system-authored, highest trust


# ── Identity / Users / Sessions ─────────────────────────────────────────────


class Identity(Base):
    """Unified principal (§3): users, services, AI employees, agents, companies."""

    __tablename__ = "identities"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(_enum_column(IdentityKind, "identity_kind"))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        _enum_column(IdentityStatus, "identity_status"), default=IdentityStatus.ACTIVE.value
    )
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)  # e.g. a human owner
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )  # company scope, if scoped
    company_scope_all: Mapped[bool] = mapped_column(Boolean, default=False)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_active: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_identities_kind_status", "kind", "status"),
        UniqueConstraint("external_ref", name="uq_identities_external_ref"),
    )


class UserAccount(Base):
    """Human login record (separate from Identity; PBKDF2-hashed password)."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("identities.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    password_salt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        _enum_column(UserStatus, "user_status"), default=UserStatus.ACTIVE.value
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bootstrap: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)


class AuthSession(Base):
    """Refresh-token session. Only token hashes are stored (never plaintext)."""

    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("identities.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256 of refresh token
    status: Mapped[str] = mapped_column(
        _enum_column(AuthSessionStatus, "auth_session_status"),
        default=AuthSessionStatus.ACTIVE.value,
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    replaced_by_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        Index("ix_auth_sessions_identity_status", "identity_id", "status"),
    )


# ── RBAC: Roles / Permissions ───────────────────────────────────────────────


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), index=True)
    code: Mapped[str] = mapped_column(String(100), index=True)
    scope: Mapped[str] = mapped_column(_enum_column(RoleScope, "role_scope"))
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("code", "scope", "company_id", name="uq_roles_code_scope_company"),
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), index=True
    )

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)


class IdentityRole(Base):
    __tablename__ = "identity_roles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("identities.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    granted_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("identity_id", "role_id", "company_id", name="uq_identity_role_company"),
    )


# ── Policy Engine ────────────────────────────────────────────────────────────


class PolicyRule(Base):
    __tablename__ = "policy_rules"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(_enum_column(PolicyScope, "policy_scope"))
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    subject_pattern: Mapped[str] = mapped_column(String(200), default="*")  # identity kind or "*"
    # e.g. external.send_message
    action_pattern: Mapped[str] = mapped_column(String(200), index=True)
    resource_pattern: Mapped[str] = mapped_column(String(200), default="*")
    effect: Mapped[str] = mapped_column(_enum_column(PolicyEffect, "policy_effect"))
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    priority: Mapped[int] = mapped_column(Integer, default=0)  # higher wins; restrictive binds
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (Index("ix_policy_rules_subject_action", "subject_pattern", "action_pattern"),)


class PolicyDecision(Base):
    """Every policy evaluation is recorded (auditable trace)."""

    __tablename__ = "policy_decisions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    identity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(String(200), index=True)
    resource: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision: Mapped[str] = mapped_column(_enum_column(PolicyDecisionType, "policy_decision"))
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    matched_rule_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    matched_rule_scope: Mapped[str | None] = mapped_column(String(30), nullable=True)
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


# ── Secrets & Encryption ────────────────────────────────────────────────────


class EncryptionKey(Base):
    __tablename__ = "encryption_keys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        _enum_column(EncryptionKeyStatus, "encryption_key_status"),
        default=EncryptionKeyStatus.ACTIVE.value,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)  # sha256 of the key bytes
    activated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # We deliberately do NOT store key material here — keys come from env only.


class Secret(Base):
    __tablename__ = "secrets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(_enum_column(SecretKind, "secret_kind"))
    status: Mapped[str] = mapped_column(
        _enum_column(SecretStatus, "secret_status"), default=SecretStatus.ACTIVE.value
    )
    ciphertext: Mapped[str] = mapped_column(Text)  # Fernet-encrypted (AES-256-GCM)
    key_id: Mapped[str] = mapped_column(String(100), index=True)  # which EncryptionKey
    mask_hint: Mapped[str | None] = mapped_column(String(40), nullable=True)  # e.g. last4
    rotation_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("name", "company_id", name="uq_secrets_name_company"),)


class SecretVersion(Base):
    """Version history for rotation/rollback; each version carries its own key id."""

    __tablename__ = "secret_versions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    secret_id: Mapped[UUID] = mapped_column(
        ForeignKey("secrets.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    ciphertext: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(
        _enum_column(SecretStatus, "secret_version_status"),
        default=SecretStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("secret_id", "version", name="uq_secret_version"),)


# ── Audit (append-only, hash-chained) ───────────────────────────────────────


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    seq: Mapped[int] = mapped_column(Integer, index=True)  # monotonic chain position
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    actor_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(
        _enum_column(AuditOutcome, "audit_outcome"), default=AuditOutcome.SUCCESS.value
    )
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    policy_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (Index("ix_audit_events_actor_action", "actor_id", "action"),)


# ── Security events, alerts, incidents ──────────────────────────────────────


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    category: Mapped[str] = mapped_column(
        _enum_column(SecurityEventCategory, "security_event_category"), index=True
    )
    severity: Mapped[str] = mapped_column(
        _enum_column(Severity, "security_event_severity"), default=Severity.LOW.value
    )
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    observed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)  # dedupe key
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (UniqueConstraint("fingerprint", name="uq_security_events_fingerprint"),)


class SecurityAlert(Base):
    __tablename__ = "security_alerts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    severity: Mapped[str] = mapped_column(
        _enum_column(Severity, "security_alert_severity"), default=Severity.MEDIUM.value
    )
    status: Mapped[str] = mapped_column(
        _enum_column(SecurityAlertStatus, "security_alert_status"),
        default=SecurityAlertStatus.OPEN.value,
    )
    rule_code: Mapped[str | None] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    event_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # referencing ids
    source_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("security_events.id", ondelete="SET NULL"), nullable=True
    )
    incident_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    alert_manager_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    severity: Mapped[str] = mapped_column(
        _enum_column(Severity, "incident_severity"), default=Severity.MEDIUM.value
    )
    status: Mapped[str] = mapped_column(
        _enum_column(IncidentStatus, "incident_status"),
        default=IncidentStatus.DETECTED.value,
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("security_alerts.id", ondelete="SET NULL"), nullable=True
    )
    timeline_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assigned_to: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    contained_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )


class IncidentAction(Base):
    """Remediation actions (§85) — every action is audited; states tracked."""

    __tablename__ = "incident_actions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    action_code: Mapped[str] = mapped_column(String(120))  # pause_company, disable_integration, ...
    target_company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    target_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    state: Mapped[str] = mapped_column(
        _enum_column(IncidentActionState, "incident_action_state"),
        default=IncidentActionState.PENDING.value,
    )
    rationale: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    performed_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    audit_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ── Kill switch / flags ─────────────────────────────────────────────────────


class SystemFlag(Base):
    __tablename__ = "system_flags"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(_enum_column(SystemFlagScope, "system_flag_scope"))
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)  # company when scoped
    flag: Mapped[str] = mapped_column(String(120))  # e.g. autonomy_paused, external_paused
    status: Mapped[str] = mapped_column(
        _enum_column(SystemFlagStatus, "system_flag_status"),
        default=SystemFlagStatus.ACTIVE.value,
    )
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    set_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    set_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cleared_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    __table_args__ = (
        UniqueConstraint("scope", "tenant_id", "flag", "status", name="uq_system_flag_active"),
    )


class BreakGlassAccess(Base):
    """§ break-glass: time-limited elevated access; explicit activation, auto-expiry."""

    __tablename__ = "break_glass_access"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("identities.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(
        _enum_column(BreakGlassStatus, "break_glass_status"),
        default=BreakGlassStatus.ACTIVE.value,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    activated_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    audit_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ── Resource governance ─────────────────────────────────────────────────────


class ResourceLimit(Base):
    __tablename__ = "resource_limits"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(_enum_column(ResourceLimitScope, "resource_limit_scope"))
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    category: Mapped[str] = mapped_column(
        _enum_column(ResourceCategory, "resource_category"), index=True
    )
    max_value: Mapped[float] = mapped_column(Float)
    period: Mapped[str | None] = mapped_column(String(20), nullable=True)  # per_run|per_day|...
    enforced: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint(
            "scope",
            "tenant_id",
            "category",
            "period",
            name="uq_resource_limit_scope_tenant_category",
        ),
    )


class ResourceUsage(Base):
    __tablename__ = "resource_usage"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    category: Mapped[str] = mapped_column(
        _enum_column(ResourceCategory, "resource_usage_category"), index=True
    )
    amount: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    instrument: Mapped[str | None] = mapped_column(String(120), nullable=True)  # invocation kind
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )


# ── Rate limiting (DB-backed window records) ────────────────────────────────


class RateLimitRecord(Base):
    __tablename__ = "rate_limit_records"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(200), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    count: Mapped[int] = mapped_column(Integer, default=0)
    limit: Mapped[int] = mapped_column(Integer)
    path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("key", "window_start", name="uq_rate_limit_key_window"),)


# ── Feature flags ───────────────────────────────────────────────────────────


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(
        _enum_column(FeatureFlagScope, "feature_flag_scope"),
        default=FeatureFlagScope.GLOBAL.value,
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("scope", "company_id", "name", name="uq_feature_flag_scope_name"),
    )


# ── Reliability: dead-letter queue & idempotency ────────────────────────────


class DeadLetterJob(Base):
    __tablename__ = "dead_letter_jobs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    workflow_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(120))
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        _enum_column(DeadLetterStatus, "dead_letter_status"),
        default=DeadLetterStatus.PENDING.value,
    )
    retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dead_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(200), index=True)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_body_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(
        _enum_column(IdempotencyOutcome, "idempotency_outcome"),
        default=IdempotencyOutcome.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("key", "company_id", "method", "path", name="uq_idempotency_key"),
    )


# ── Health / observability records ──────────────────────────────────────────


class SystemHealthRecord(Base):
    __tablename__ = "system_health_records"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    service: Mapped[str] = mapped_column(String(80))
    component: Mapped[str] = mapped_column(String(80), index=True)  # db|redis|worker|api
    healthy: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )


# ── Data governance: classification, retention, controls ────────────────────


class DataClassificationRecord(Base):
    __tablename__ = "data_classifications"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    classification: Mapped[str] = mapped_column(
        _enum_column(DataClassification, "data_classification"), index=True
    )
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(64), index=True)
    sensitivity_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    policy_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", name="uq_data_classification_resource"),
    )


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(
        _enum_column(RetentionEntityType, "retention_entity_type"), index=True
    )
    retention_days: Mapped[int] = mapped_column(Integer, default=180)
    deletion_semantics: Mapped[str] = mapped_column(
        _enum_column(DeletionSemantics, "deletion_semantics"),
        default=DeletionSemantics.SOFT.value,
    )
    retention_lock: Mapped[bool] = mapped_column(Boolean, default=False)  # no casual deletion
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    changed_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("entity_type", "company_id", name="uq_retention_policy_entity_company"),
    )


class GovernanceControl(Base):
    """Human-readable registry of every enforcement rule (§51/§52/§53)."""

    __tablename__ = "governance_controls"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    category: Mapped[str] = mapped_column(String(80), index=True)  # identity|policy|approval|...
    enforcement_scope: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enforced: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


# ── Context authority (Wave G: prompt-injection boundary) ───────────────────


class ContextAuthorityRecord(Base):
    __tablename__ = "context_authorities"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(80))  # browser_observation|web_content|...
    authority: Mapped[str] = mapped_column(_enum_column(ContextAuthority, "context_authority"))
    resource_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    qualified_by: Mapped[str | None] = mapped_column(String(200), nullable=True)  # provenance
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("source_type", "resource_ref", name="uq_context_authority_source_ref"),
    )
