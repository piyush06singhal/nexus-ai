"""Security domain schemas (Phase 11).

Never serialize secret values, ciphertext, plaintext passwords, or stack
traces. Secret rows render as references plus a masked hint only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.security import DeletionSemantics


class _StrictModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


def _password_validator(v: str) -> str:
    if len(v) < 10:
        raise ValueError("Password must be at least 10 characters.")
    return v


# ── Auth ─────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class IdentityPublic(_StrictModel):
    id: UUID | None = None
    kind: str
    name: str
    status: str
    company_id: UUID | None = None
    external_ref: str | None = None


class UserPublic(_StrictModel):
    id: UUID
    identity_id: UUID
    email: str
    display_name: str
    status: str


class SessionResultDTO(BaseModel):
    access_token: str
    refresh_token: str
    session_id: UUID
    identity: IdentityPublic
    user: UserPublic | None = None
    company_id: UUID | None = None


class SessionInfo(_StrictModel):
    id: UUID
    identity_id: UUID
    company_id: UUID | None = None
    status: str
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class AuthSessionResponse(BaseModel):
    identity: IdentityPublic
    user: UserPublic | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


# ── Generic security entity views ───────────────────────────────────────────


class SecretReference(_StrictModel):
    """A secret rendered as a reference + hint — never its value."""

    id: UUID
    name: str
    company_id: UUID | None = None
    kind: str
    status: str
    mask_hint: str | None = None
    key_id: str
    rotation_due_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    plaintext: str = Field(min_length=1)
    company_id: UUID | None = None
    kind: str = "operator"
    rotation_days: int | None = None


class IdentityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = "user"
    company_id: UUID | None = None
    external_ref: str | None = None


class UserCreate(BaseModel):
    email: str
    display_name: str
    password: str = Field(min_length=10)
    company_id: UUID | None = None
    roles: list[str] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return _password_validator(v)


class RolePublic(_StrictModel):
    id: UUID
    name: str
    code: str
    scope: str
    company_id: UUID | None = None
    description: str | None = None
    builtin: bool = False


class PermissionPublic(_StrictModel):
    id: UUID
    code: str
    description: str | None = None
    category: str | None = None
    builtin: bool = False


class RoleAssignRequest(BaseModel):
    roles: list[str] = Field(min_length=1)
    company_id: UUID | None = None


class UserCreateResponse(BaseModel):
    identity: IdentityPublic
    user: UserPublic
    roles: list[str] = Field(default_factory=list)


# ── Policy ───────────────────────────────────────────────────────────────────


class PolicyRuleCreate(BaseModel):
    scope: str = "company"
    company_id: UUID | None = None
    subject_pattern: str = "*"
    action_pattern: str
    resource_pattern: str = "*"
    effect: str  # allow | deny | require_approval
    risk_level: str = "low"
    priority: int = 0
    reason: str | None = None
    enabled: bool = True


class PolicyRulePublic(_StrictModel):
    id: UUID
    scope: str
    company_id: UUID | None = None
    subject_pattern: str
    action_pattern: str
    resource_pattern: str
    effect: str
    risk_level: str
    priority: int
    reason: str | None = None
    enabled: bool
    created_at: datetime


class PolicyDecisionPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    identity_id: UUID | None = None
    action: str
    resource: str | None = None
    decision: str
    reason: str | None = None
    matched_rule_scope: str | None = None
    created_at: datetime


# ── Audit ────────────────────────────────────────────────────────────────────


class AuditEventPublic(_StrictModel):
    id: UUID
    seq: int
    company_id: UUID | None = None
    actor_id: UUID | None = None
    actor_name: str | None = None
    action: str
    category: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    outcome: str
    detail: dict[str, Any] | None = None
    policy_result: str | None = None
    approval_ref: str | None = None
    correlation_id: str | None = None
    ip_address: str | None = None
    hash: str
    prev_hash: str | None = None
    created_at: datetime


class AuditChainVerify(BaseModel):
    verified: bool
    checked: int
    first_gap_at_seq: int | None = None


# ── Security events / alerts / incidents ────────────────────────────────────


class SecurityEventPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    category: str
    severity: str
    title: str
    detail: dict[str, Any] | None = None
    actor_id: UUID | None = None
    created_at: datetime


class SecurityAlertPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    severity: str
    status: str
    rule_code: str | None = None
    title: str
    description: str | None = None
    created_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


class SecurityAlertResolve(BaseModel):
    resolution: str | None = None


class IncidentCreate(BaseModel):
    company_id: UUID | None = None
    severity: str = "medium"
    title: str = Field(min_length=1)
    description: str | None = None
    alert_ids: list[UUID] = Field(default_factory=list)


class IncidentPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    severity: str
    status: str
    title: str
    description: str | None = None
    timeline_json: dict[str, Any] | None = None
    contained_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime


class IncidentTransition(BaseModel):
    to_status: str
    note: str | None = None


class IncidentActionRequest(BaseModel):
    incident_id: UUID
    action: str
    params: dict | None = None


class IncidentActionPublic(_StrictModel):
    id: UUID
    incident_id: UUID
    action_code: str
    target_company_id: UUID | None = None
    target_ref: str | None = None
    state: str
    performed_by: UUID | None = None
    result_json: dict[str, Any] | None = None
    created_at: datetime
    applied_at: datetime | None = None


class IncidentDetailPublic(IncidentPublic):
    """Incident response enriched with linked alerts and containment actions."""

    alerts: list[SecurityAlertPublic] = Field(default_factory=list)
    actions: list[IncidentActionPublic] = Field(default_factory=list)


# ── Governance ───────────────────────────────────────────────────────────────


class SystemFlagPublic(_StrictModel):
    id: UUID
    scope: str
    tenant_id: UUID | None = None
    flag: str
    status: str
    reason: str | None = None
    set_by: UUID | None = None
    set_at: datetime
    cleared_at: datetime | None = None


class FlagSetRequest(BaseModel):
    flag: str
    reason: str | None = None
    tenant_id: UUID | None = None


class BreakGlassRequest(BaseModel):
    scope: str = "*"
    reason: str = Field(min_length=1)
    max_minutes: int | None = None


class BreakGlassPublic(_StrictModel):
    id: UUID
    identity_id: UUID
    company_id: UUID | None = None
    scope: str
    reason: str
    status: str
    requested_at: datetime
    expires_at: datetime
    approved_by: UUID | None = None
    revoked_at: datetime | None = None


class ResourceLimitPublic(_StrictModel):
    id: UUID
    scope: str
    tenant_id: UUID | None = None
    category: str
    max_value: float
    period: str | None = None
    enforced: bool


class ResourceUsagePublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    tenant_id: UUID | None = None
    actor_id: UUID | None = None
    category: str
    amount: float
    unit: str | None = None
    instrument: str | None = None
    recorded_at: datetime


class ResourceLimitSetRequest(BaseModel):
    scope: str = "company"
    tenant_id: UUID | None = None
    category: str
    max_value: float
    period: str | None = "per_run"
    enforced: bool = True


class FeatureFlagPublic(_StrictModel):
    id: UUID
    scope: str
    company_id: UUID | None = None
    name: str
    enabled: bool
    rationale: str | None = None
    updated_at: datetime


class FeatureFlagSetRequest(BaseModel):
    name: str
    enabled: bool
    company_id: UUID | None = None
    rationale: str | None = None


class GovernanceControlPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    code: str
    title: str
    description: str | None = None
    category: str
    enforced: bool
    source: str | None = None


# ── Health / metrics ─────────────────────────────────────────────────────────


class SystemHealthRecordPublic(_StrictModel):
    id: UUID
    service: str
    component: str
    healthy: bool
    detail: dict[str, Any] | None = None
    latency_ms: float | None = None
    recorded_at: datetime


class HealthProbe(BaseModel):
    component: str
    healthy: bool
    latency_ms: float | None = None
    detail: dict[str, Any] | None = None


class SystemHealthProbe(BaseModel):
    status: str
    service: str
    checks: dict[str, str] | None = None


class HealthOverview(BaseModel):
    incidents_open: int
    alerts_open: int
    audit_events: int
    resource_limits: int
    resource_usage_entries: int


class MetricsSnapshot(BaseModel):
    labels: dict[str, str]
    values: dict[str, float]
    counters: dict[str, int]
    recorded_at: datetime


# ── Data protection: classification, transfer policy, retention ─────────────


class DataClassificationSetRequest(BaseModel):
    resource_type: str
    resource_id: str
    classification: str
    sensitivity_reason: str | None = None


class DataClassificationPublic(_StrictModel):
    resource_type: str
    resource_id: str
    classification: str
    sensitivity_reason: str | None = None


class TransferCheckRequest(BaseModel):
    resource_type: str
    resource_id: str
    destination: str
    payload: dict | None = None
    max_outbound: str | None = None


class TransferDecisionPublic(_StrictModel):
    allowed: bool
    reason: str
    target_classification: str
    destination: str | None = None
    requires_approval: bool = False
    blocked_fields: int = 0


class RetentionPolicySetRequest(BaseModel):
    entity_type: str
    retention_days: int
    deletion_semantics: str = DeletionSemantics.SOFT.value
    retention_lock: bool = False


class RetentionPolicyPublic(_StrictModel):
    entity_type: str
    company_id: UUID | None = None
    retention_days: int
    deletion_semantics: str
    retention_lock: bool
    enabled: bool
