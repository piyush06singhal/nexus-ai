"""AI Company domain models (Phase 8).

The organizational layer above the AI Employee OS (Phase 7). Models the
organizational structure: company, departments, organizational roles and
memberships, plus the organizational-intelligence entities — goals, KPIs,
budgets (resource accounting), policies, decisions, risks, alerts, reports,
and the audit/timeline event log.

Design notes (mirroring project convention):
- Structured fields (mission, values, priorities, options, evidence, …) are
  stored as JSON Text blobs so the relational columns carry identity/lifecycle/
  state.
- Enum columns use the project's ``_enum_values`` / ``native_enum=False`` /
  ``create_constraint=False`` convention.
- Several cross-cutting entities (goals, KPIs, budgets, policies, risks,
  alerts) are **scope-discriminated**: a single table carries ``scope_type``
  + ``scope_id`` so the same entity works at company, department, or (where
  sensible) employee granularity, matching the spec's "scoped to company,
  department, or employee" language. Employee-scoped accounting/goals still
  live in the Phase 7 ``employee_budgets`` / ``employee_goals`` tables so the
  existing Employee OS is untouched.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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


class CompanyStatus(StrEnum):
    """Lifecycle status for an AI company."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class DepartmentStatus(StrEnum):
    """Lifecycle status for a department."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class AuthorityLevel(StrEnum):
    """Organizational authority levels."""

    INDIVIDUAL_CONTRIBUTOR = "individual_contributor"
    TEAM_LEAD = "team_lead"
    MANAGER = "manager"
    EXECUTIVE = "executive"
    COMPANY_ADMIN = "company_admin"


class GoalScopeType(StrEnum):
    """Granularity a goal is scoped to."""

    COMPANY = "company"
    DEPARTMENT = "department"
    EMPLOYEE = "employee"


class GoalStatusOrg(StrEnum):
    """Lifecycle status for an organizational goal."""

    NOT_STARTED = "not_started"
    ACTIVE = "active"
    AT_RISK = "at_risk"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PolicyScopeType(StrEnum):
    """Granularity a policy belongs to (system = global, applies to all)."""

    SYSTEM = "system"
    COMPANY = "company"
    DEPARTMENT = "department"


class DecisionStatus(StrEnum):
    """Lifecycle status for a decision request."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RiskStatus(StrEnum):
    """Lifecycle status for a risk."""

    OPEN = "open"
    MITIGATING = "mitigating"
    MONITORED = "monitored"
    RESOLVED = "resolved"
    ACCEPTED = "accepted"


class AlertSeverity(StrEnum):
    """Severity classification for an operational alert."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFORMATIONAL = "informational"


class AlertStatus(StrEnum):
    """Lifecycle status for an alert."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class KpiCategory(StrEnum):
    """Category for a KPI."""

    QUALITY = "quality"
    PRODUCTIVITY = "productivity"
    RELIABILITY = "reliability"
    COST = "cost"
    SPEED = "speed"
    GOAL_PROGRESS = "goal_progress"
    RESOURCE_UTILIZATION = "resource_utilization"
    CUSTOMER = "customer"
    OPERATIONAL = "operational"


class DecisionVerdict(StrEnum):
    """Verdict recorded in a decision review."""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"


# ── Company ──────────────────────────────────────────────────────────────────


class Company(Base):
    """A first-class AI company entity.

    Identity is independent of execution state: the company carries its
    mission, vision, industry, values, and strategic priorities regardless of
    what work is currently running underneath it.
    """

    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mission: Mapped[str | None] = mapped_column(Text, nullable=True)
    vision: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    values: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    strategic_priorities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    status: Mapped[CompanyStatus] = mapped_column(
        _enum_column(CompanyStatus, "company_status"),
        nullable=False,
        default=CompanyStatus.DRAFT,
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    policies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON seed
    resource_limits: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    budget_config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Company id={self.id} name={self.name!r} status={self.status.value}>"


# ── Departments ──────────────────────────────────────────────────────────────


class Department(Base):
    """A department within a company.

    Supports nested hierarchies via ``parent_department_id`` (Engineering →
    Backend / Frontend / AI Systems).
    """

    __tablename__ = "departments"
    __table_args__ = (
        Index("ix_departments_company_parent", "company_id", "parent_department_id"),
        Index("ix_departments_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mission: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    parent_department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[DepartmentStatus] = mapped_column(
        _enum_column(DepartmentStatus, "department_status"),
        nullable=False,
        default=DepartmentStatus.DRAFT,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Department id={self.id} name={self.name!r}>"


# ── Organizational roles / memberships ───────────────────────────────────────


class OrganizationalRole(Base):
    """A reusable organizational role definition.

    Roles are distinct from the underlying Agent — a role is organizational
    (title, responsibilities, authority, KPIs) and can be occupied by an AI
    Employee.
    """

    __tablename__ = "organizational_roles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    required_skills: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    authority_level: Mapped[AuthorityLevel] = mapped_column(
        _enum_column(AuthorityLevel, "authority_level"),
        nullable=False,
        default=AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
    )
    authority_scope: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    default_policies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    kpis: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    compatible_departments: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrganizationalMembership(Base):
    """An employee's membership in a company (with optional department + role).

    This is the Phase 8 Employee OS integration point: the membership ties an
    existing Phase 7 :class:`AIEmployee` into the organizational hierarchy
    (company → department) plus a role and a manager — without creating a
    second employee model.
    """

    __tablename__ = "organizational_memberships"
    __table_args__ = (
        Index("ix_org_memberships_company", "company_id"),
        Index("ix_org_memberships_department", "department_id"),
        Index("ix_org_memberships_manager", "manager_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    role_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("organizational_roles.id", ondelete="SET NULL"), nullable=True
    )
    responsibility: Mapped[str] = mapped_column(String(16), nullable=False, default="ic")
    manager_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Goals (scope-discriminated) ──────────────────────────────────────────────


class OrgGoal(Base):
    """A hierarchical organizational goal.

    Scoped to company / department / employee via ``scope_type`` + ``scope_id``.
    ``parent_goal_id`` enables the cascading goal tree:
    Company Goal → Department Goal → Employee Goal.
    """

    __tablename__ = "org_goals"
    __table_args__ = (
        Index("ix_org_goals_company_scope", "company_id", "scope_type", "scope_id"),
        Index("ix_org_goals_parent", "parent_goal_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[GoalScopeType] = mapped_column(
        _enum_column(GoalScopeType, "goal_scope_type"),
        nullable=False,
        default=GoalScopeType.COMPANY,
    )
    scope_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    parent_goal_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("org_goals.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metric: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[GoalStatusOrg] = mapped_column(
        _enum_column(GoalStatusOrg, "goal_status_org"),
        nullable=False,
        default=GoalStatusOrg.NOT_STARTED,
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── KPIs (scope-discriminated) ───────────────────────────────────────────────


class KPI(Base):
    """A reusable KPI definition, scoped to company/department/employee.

    ``source_metric`` names the authoritative NEXUS data source used to compute
    the value (e.g. ``task_success_rate``, ``verification_rate``,
    ``budget_utilization``). Values are computed server-side by :class:`KPIService`
    from real operational data — never submitted by the frontend.
    """

    __tablename__ = "kpis"
    __table_args__ = (
        Index("ix_kpis_company_scope", "company_id", "scope_type", "scope_id"),
        Index("ix_kpis_category", "category"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[GoalScopeType] = mapped_column(
        _enum_column(GoalScopeType, "kpi_scope_type"),
        nullable=False,
        default=GoalScopeType.COMPANY,
    )
    scope_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[KpiCategory] = mapped_column(
        _enum_column(KpiCategory, "kpi_category"),
        nullable=False,
        default=KpiCategory.OPERATIONAL,
    )
    source_metric: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    frequency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON config

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KpiValue(Base):
    """A computed KPI reading at a point in time (historical series)."""

    __tablename__ = "kpi_values"
    __table_args__ = (Index("ix_kpi_values_kpi_recorded", "kpi_id", "recorded_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    kpi_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("kpis.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    variance: Mapped[float | None] = mapped_column(Float, nullable=True)  # target delta
    trend: Mapped[str | None] = mapped_column(String(16), nullable=True)  # declining/flat/improving
    period_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Budgets (resource accounting, scope-discriminated) ───────────────────────


class Budget(Base):
    """Company / department resource accounting.

    Employee-scoped budgets live in the Phase 7 ``employee_budgets`` table.
    This table covers company and department granularity; the effective limit
    for an execution is the most restrictive of company + department + employee.
    """

    __tablename__ = "budgets"
    __table_args__ = (Index("ix_budgets_company_scope", "company_id", "scope_type", "scope_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[GoalScopeType] = mapped_column(
        _enum_column(GoalScopeType, "budget_scope_type"),
        nullable=False,
        default=GoalScopeType.COMPANY,
    )
    scope_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    monthly_limit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    allocated: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reserved: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    spent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_used: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tool_calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Policies (scope-discriminated, most-restrictive-wins) ────────────────────


class Policy(Base):
    """A company/department policy entry.

    ``scope_type=system`` (+ null company) represents a global policy that
    applies to every company. Resolution walks system → company → department →
    (employee profile) → (task) and takes the **most restrictive** applicable
    value for each key.
    """

    __tablename__ = "policies"
    __table_args__ = (Index("ix_policies_scope", "company_id", "scope_type", "scope_id", "key"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    scope_type: Mapped[PolicyScopeType] = mapped_column(
        _enum_column(PolicyScopeType, "policy_scope_type"),
        nullable=False,
        default=PolicyScopeType.COMPANY,
    )
    scope_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Decisions ────────────────────────────────────────────────────────────────


class Decision(Base):
    """A structured decision request.

    Preserves concise rationale + supporting evidence only — never private
    chain-of-thought. Requires authorized review; not autonomous execution.
    """

    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decisions_company_status", "company_id", "status"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    requester_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    decision_maker_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    options: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list
    selected_option: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)  # concise summary
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    risk: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    budget_impact: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    required_authority: Mapped[AuthorityLevel] = mapped_column(
        _enum_column(AuthorityLevel, "decision_authority"),
        nullable=False,
        default=AuthorityLevel.EXECUTIVE,
    )
    status: Mapped[DecisionStatus] = mapped_column(
        _enum_column(DecisionStatus, "decision_status"),
        nullable=False,
        default=DecisionStatus.DRAFT,
    )
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DecisionReview(Base):
    """An audit trail entry for a decision lifecycle action."""

    __tablename__ = "decision_reviews"
    __table_args__ = (Index("ix_decision_reviews_decision", "decision_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[DecisionVerdict | None] = mapped_column(
        _enum_column(DecisionVerdict, "decision_verdict"), nullable=True
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Risks / Alerts ───────────────────────────────────────────────────────────


class Risk(Base):
    """A company/department risk register entry."""

    __tablename__ = "risks"
    __table_args__ = (
        Index("ix_risks_company_scope", "company_id", "scope_type", "scope_id"),
        Index("ix_risks_severity", "severity"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[GoalScopeType] = mapped_column(
        _enum_column(GoalScopeType, "risk_scope_type"),
        nullable=False,
        default=GoalScopeType.COMPANY,
    )
    scope_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact: Mapped[str | None] = mapped_column(String(256), nullable=True)
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[RiskStatus] = mapped_column(
        _enum_column(RiskStatus, "risk_status"),
        nullable=False,
        default=RiskStatus.OPEN,
    )
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Alert(Base):
    """An operational alert, persisted from threshold checks."""

    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_company_severity", "company_id", "severity", "status"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[GoalScopeType] = mapped_column(
        _enum_column(GoalScopeType, "alert_scope_type"),
        nullable=False,
        default=GoalScopeType.COMPANY,
    )
    scope_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(
        _enum_column(AlertSeverity, "alert_severity"),
        nullable=False,
        default=AlertSeverity.WARNING,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        _enum_column(AlertStatus, "alert_status"),
        nullable=False,
        default=AlertStatus.ACTIVE,
    )
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Reports ──────────────────────────────────────────────────────────────────


class CompanyReport(Base):
    """A stored organizational report.

    ``recommendations`` are explicitly non-executing; ``evidence`` links the
    report back to the authoritative data it was computed from.
    """

    __tablename__ = "company_reports"
    __table_args__ = (Index("ix_company_reports_company_created", "company_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(32), nullable=False, default="weekly")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    highlights: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    blockers: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    goal_progress: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unverified"
    )
    verification_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Audit / timeline events ──────────────────────────────────────────────────


class OrgEvent(Base):
    """A unified organizational timeline / audit event.

    Records organizational changes (company created, department created,
    employee added, goal created, decision approved, alert generated, …) with
    actor, target, action, outcome, and correlation id so the full history is
    auditable and traceable to company / department / employee.
    """

    __tablename__ = "organizational_events"
    __table_args__ = (
        Index("ix_org_events_company_created", "company_id", "created_at"),
        Index("ix_org_events_action", "action"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
