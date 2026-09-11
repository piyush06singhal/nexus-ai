"""Pydantic API schemas for the AI Company Layer (Phase 8).

Mirror the ORM models in :mod:`app.db.models.company` while staying decoupled
from SQLAlchemy, matching the other schema modules (``task.py``, ``employee.py``)
so they validate input and serialize output without leaking ORM state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.company import (
    AlertSeverity,
    AlertStatus,
    AuthorityLevel,
    CompanyStatus,
    DecisionStatus,
    DecisionVerdict,
    DepartmentStatus,
    GoalScopeType,
    GoalStatusOrg,
    KpiCategory,
    PolicyScopeType,
    RiskStatus,
)

# ── Company ─────────────────────────────────────────────────────────────


class CompanyCreate(BaseModel):
    """Payload to create a company."""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    mission: str | None = None
    vision: str | None = None
    industry: str | None = None
    timezone: str | None = None
    currency: str | None = "USD"


class CompanyUpdate(BaseModel):
    """Partial update payload for a company."""

    name: str | None = None
    description: str | None = None
    mission: str | None = None
    vision: str | None = None
    industry: str | None = None
    timezone: str | None = None
    currency: str | None = None
    values: list[str] | None = None
    strategic_priorities: list[str] | None = None


class CompanyRead(BaseModel):
    """Full company representation returned by the API."""

    id: UUID
    name: str
    slug: str | None = None
    description: str | None = None
    mission: str | None = None
    vision: str | None = None
    industry: str | None = None
    timezone: str | None = None
    currency: str | None = None
    values: list[str] | None = None
    strategic_priorities: list[str] | None = None
    status: CompanyStatus
    owner_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CompanyList(BaseModel):
    """Paginated company list."""

    items: list[CompanyRead]
    total: int


# ── Department ──────────────────────────────────────────────────────────


class DepartmentCreate(BaseModel):
    """Payload to create a department."""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    mission: str | None = None
    manager_id: UUID | None = None
    parent_department_id: UUID | None = None


class DepartmentUpdate(BaseModel):
    """Partial update payload for a department."""

    name: str | None = None
    description: str | None = None
    mission: str | None = None
    manager_id: UUID | None = None
    parent_department_id: UUID | None = None


class DepartmentRead(BaseModel):
    """Full department representation returned by the API."""

    id: UUID
    company_id: UUID
    name: str
    description: str | None = None
    mission: str | None = None
    manager_id: UUID | None = None
    parent_department_id: UUID | None = None
    status: DepartmentStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Membership / roles ─────────────────────────────────────────────────


class MembershipCreate(BaseModel):
    """Add an employee to a company with department/role/manager."""

    employee_id: UUID
    department_id: UUID | None = None
    role_id: UUID | None = None
    manager_id: UUID | None = None
    responsibility: str | None = "ic"


class MembershipRead(BaseModel):
    """An organizational membership."""

    id: UUID
    company_id: UUID
    employee_id: UUID
    department_id: UUID | None = None
    role_id: UUID | None = None
    manager_id: UUID | None = None
    responsibility: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MembershipUpdate(BaseModel):
    """Partial update for a membership (department/role/manager/responsibility)."""

    department_id: UUID | None = None
    role_id: UUID | None = None
    manager_id: UUID | None = None
    responsibility: str | None = None


class OrgRoleCreate(BaseModel):
    """Payload to create an organizational role."""

    name: str = Field(min_length=1, max_length=128)
    title: str | None = None
    authority_level: AuthorityLevel = AuthorityLevel.INDIVIDUAL_CONTRIBUTOR
    responsibilities: list[str] | None = None
    required_skills: list[str] | None = None
    default_policies: list[str] | None = None


class OrgRoleRead(BaseModel):
    """An organizational role."""

    id: UUID
    company_id: UUID | None = None
    name: str
    title: str | None = None
    authority_level: AuthorityLevel
    responsibilities: list[str] | None = None
    required_skills: list[str] | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Goals ───────────────────────────────────────────────────────────────


class GoalCreate(BaseModel):
    """Payload to create a company/department/employee goal."""

    scope_type: GoalScopeType
    scope_id: UUID
    title: str = Field(min_length=1, max_length=256)
    description: str | None = None
    parent_goal_id: UUID | None = None
    priority: int | None = None
    target: float | None = None
    metric: str | None = None
    deadline: datetime | None = None
    owner_id: UUID | None = None


class GoalUpdate(BaseModel):
    """Partial update payload for a goal."""

    title: str | None = None
    description: str | None = None
    priority: int | None = None
    target: float | None = None
    metric: str | None = None
    deadline: datetime | None = None
    status: GoalStatusOrg | None = None


class GoalRead(BaseModel):
    """Full goal representation returned by the API."""

    id: UUID
    company_id: UUID
    scope_type: GoalScopeType
    scope_id: UUID
    parent_goal_id: UUID | None = None
    title: str
    description: str | None = None
    priority: int | None = None
    target: float | None = None
    metric: str | None = None
    deadline: datetime | None = None
    status: GoalStatusOrg
    progress: float | None = None
    owner_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── KPIs ────────────────────────────────────────────────────────────────


class KpiCreate(BaseModel):
    """Payload to create a KPI bound to an authoritative source metric."""

    scope_type: GoalScopeType
    scope_id: UUID
    name: str = Field(min_length=1, max_length=128)
    source_metric: str
    description: str | None = None
    category: KpiCategory | None = None
    target: float | None = None
    unit: str | None = None
    owner_id: UUID | None = None
    frequency: str | None = None


class KpiRead(BaseModel):
    """Full KPI representation with current/history values."""

    id: UUID
    company_id: UUID
    scope_type: GoalScopeType
    scope_id: UUID
    name: str
    description: str | None = None
    category: KpiCategory
    source_metric: str
    target: float | None = None
    unit: str | None = None
    owner_id: UUID | None = None
    frequency: str | None = None
    current_value: float | None = None
    variance: float | None = None
    trend: str | None = None
    recorded_at: datetime | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


# ── Budget ──────────────────────────────────────────────────────────────


class BudgetRead(BaseModel):
    """A budget snapshot for company/department scope."""

    company_id: UUID
    scope_type: str
    scope_id: UUID
    monthly_limit: float
    allocated: float
    reserved: float
    spent: float
    tokens_used: int
    cost_used: float
    tool_calls_used: int
    execution_count: int
    period_start: datetime | None = None
    period_end: datetime | None = None


class BudgetAllocation(BaseModel):
    """Adjust a budget's limit/allocation."""

    monthly_limit: float | None = None
    allocated: float | None = None


# ── Policies ────────────────────────────────────────────────────────────


class PolicyCreate(BaseModel):
    """Payload to create a policy."""

    scope_type: PolicyScopeType
    scope_id: UUID | None = None
    name: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=128)
    value: Any
    priority: int = 0
    enabled: bool = True


class PolicyRead(BaseModel):
    """A policy definition."""

    id: UUID
    company_id: UUID | None = None
    scope_type: PolicyScopeType
    scope_id: UUID | None = None
    name: str
    key: str
    value: Any
    priority: int
    enabled: bool
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EffectivePolicy(BaseModel):
    """The resolved most-restrictive policy value for a key."""

    key: str
    value: Any
    source_scope: str
    source_name: str | None = None
    candidates_checked: int


# ── Decisions ───────────────────────────────────────────────────────────


class DecisionCreate(BaseModel):
    """Payload to create a decision request."""

    question: str = Field(min_length=1, max_length=512)
    options: list[dict[str, Any]] = Field(min_length=1)
    context: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    rationale: str | None = None
    risk_level: str = "low"
    risk: dict[str, Any] | None = None
    budget_impact: dict[str, Any] | None = None
    required_authority: AuthorityLevel = AuthorityLevel.EXECUTIVE
    requester_id: UUID | None = None


class DecisionReviewRead(BaseModel):
    """A single decision review / audit entry."""

    id: UUID
    decision_id: UUID
    reviewer_id: UUID | None = None
    action: str
    verdict: DecisionVerdict | None = None
    rationale: str | None = None
    previous_status: str | None = None
    next_status: str | None = None
    created_at: datetime | None = None


class DecisionRead(BaseModel):
    """Full decision representation returned by the API."""

    id: UUID
    company_id: UUID
    requester_id: UUID | None = None
    decision_maker_id: UUID | None = None
    question: str
    context: dict[str, Any] | None = None
    options: list[dict[str, Any]]
    selected_option: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    rationale: str | None = None
    risk_level: str
    risk: dict[str, Any] | None = None
    budget_impact: dict[str, Any] | None = None
    required_authority: AuthorityLevel
    status: DecisionStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DecisionReviewAction(BaseModel):
    """Payload to approve/reject a decision."""

    rationale: str = Field(min_length=1)


# ── Risks ───────────────────────────────────────────────────────────────


class RiskCreate(BaseModel):
    """Payload to create a risk."""

    scope_type: GoalScopeType
    scope_id: UUID
    title: str = Field(min_length=1, max_length=256)
    description: str | None = None
    severity: str = "medium"
    probability: float | None = None
    impact: str | None = None
    owner_id: UUID | None = None
    mitigation: str | None = None


class RiskUpdate(BaseModel):
    """Partial update payload for a risk."""

    status: RiskStatus | None = None
    severity: str | None = None
    mitigation: str | None = None


class RiskRead(BaseModel):
    """Full risk representation returned by the API."""

    id: UUID
    company_id: UUID
    scope_type: GoalScopeType
    scope_id: UUID
    title: str
    description: str | None = None
    severity: str
    probability: float | None = None
    impact: str | None = None
    owner_id: UUID | None = None
    status: RiskStatus
    mitigation: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Alerts ──────────────────────────────────────────────────────────────


class AlertRead(BaseModel):
    """Full alert representation returned by the API."""

    id: UUID
    company_id: UUID
    scope_type: GoalScopeType
    scope_id: UUID
    title: str
    severity: AlertSeverity
    category: str
    message: str
    status: AlertStatus
    payload: dict[str, Any] | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Reports ─────────────────────────────────────────────────────────────


class ReportRead(BaseModel):
    """Full organizational report representation returned by the API."""

    id: UUID
    company_id: UUID
    report_type: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    created_at: datetime | None = None
    metrics: dict[str, Any] | None = None
    highlights: list[str] | None = None
    risks: list[dict[str, Any]] | None = None
    blockers: list[str] | None = None
    goal_progress: dict[str, Any] | None = None
    recommendations: list[str] | None = None
    evidence: dict[str, Any] | None = None
    verification_status: str
    verification_summary: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ReportGenerate(BaseModel):
    """Payload to generate a report."""

    report_type: str = "weekly"
    period_start: datetime | None = None
    period_end: datetime | None = None


# ── Org chart / health / analytics / timeline ──────────────────────────


class OrgChartNodeRead(BaseModel):
    """A node in the organization chart."""

    id: UUID
    type: str
    name: str
    status: str | None = None
    children: list[OrgChartNodeRead] = Field(default_factory=list)


class CompanyHealthRead(BaseModel):
    """Company health snapshot across six dimensions."""

    company_id: UUID
    overall_score: float
    status: str
    dimensions: dict[str, float]
    weights: dict[str, int]
    computed_at: datetime | None = None


class OrgEventRead(BaseModel):
    """A single organizational timeline / audit event."""

    id: UUID
    company_id: UUID | None = None
    actor: str | None = None
    action: str
    target_type: str | None = None
    target_id: UUID | None = None
    details: dict[str, Any] | None = None
    outcome: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
