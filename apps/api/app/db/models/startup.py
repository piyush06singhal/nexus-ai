"""Autonomous Startup Engine domain models (Phase 9).

The mission layer above the AI Company Layer (Phase 8). Models a startup from
mission → strategic/startup planning → organizational blueprint → controlled
workforce provisioning → products/projects → an autonomous operating cycle with
feedback and replanning — all governed by bounded autonomy.

Design notes (mirroring project convention):
- Rich payloads (analysis, plans, criteria, matrices, verdicts) are stored as
  JSON Text blobs; the relational columns carry identity/lifecycle/state.
- Enum columns use the project's ``_enum_values`` / ``native_enum=False`` /
  ``create_constraint=False`` convention.
- Every table is company-scoped (``company_id``) so a mission, product, cycle,
  lesson, gate, or graph edge never leaks across companies.
- The engine is *governance-first*: autonomous actions are prescriptive
  (``autonomy_policies``), anything risky requires an ``approval_gates`` row,
  and every step is traceable through ``mission_graph_edges``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class MissionStatus(StrEnum):
    """Lifecycle status for a startup mission."""

    DRAFT = "draft"
    ANALYZING = "analyzing"
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StrategicPlanStatus(StrEnum):
    """Lifecycle status for a strategic plan."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class StartupPlanStatus(StrEnum):
    """Lifecycle status for a startup plan."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    BOOTSTRAPPING = "bootstrapping"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProductStatus(StrEnum):
    """Lifecycle status for a product."""

    IDEA = "idea"
    DISCOVERY = "discovery"
    VALIDATION = "validation"
    PLANNING = "planning"
    BUILDING = "building"
    TESTING = "testing"
    READY_FOR_LAUNCH = "ready_for_launch"
    LAUNCHED = "launched"
    MEASURING = "measuring"
    ITERATING = "iterating"
    PAUSED = "paused"
    RETIRED = "retired"


class StartupProjectStatus(StrEnum):
    """Lifecycle status for a startup project."""

    PLANNED = "planned"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ExecutionPlanStatus(StrEnum):
    """Lifecycle status for an execution plan."""

    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperatingCycleStatus(StrEnum):
    """Lifecycle status for an autonomous operating cycle."""

    INITIALIZING = "initializing"
    OBSERVING = "observing"
    ASSESSING = "assessing"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    MEASURING = "measuring"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LessonType(StrEnum):
    """Classification for a recorded startup lesson."""

    LESSON = "lesson"
    DECISION_OUTCOME = "decision_outcome"
    FAILED_ASSUMPTION = "failed_assumption"
    SUCCESS_PATTERN = "success_pattern"
    PROCESS_IMPROVEMENT = "process_improvement"
    STRATEGIC_INSIGHT = "strategic_insight"


class ApprovalGateType(StrEnum):
    """What an approval gate governs (human decision point)."""

    MISSION_APPROVAL = "mission_approval"
    STRATEGY_APPROVAL = "strategy_approval"
    COMPANY_BOOTSTRAP_APPROVAL = "company_bootstrap_approval"
    WORKFORCE_APPROVAL = "workforce_approval"
    BUDGET_APPROVAL = "budget_approval"
    PRODUCT_LAUNCH_APPROVAL = "product_launch_approval"
    HIGH_RISK_ACTION_APPROVAL = "high_risk_action_approval"
    MAJOR_STRATEGIC_CHANGE_APPROVAL = "major_strategic_change_approval"
    # Phase 10: human gate over a high/irreversible external action. A single
    # approved EXTERNAL_ACTION_APPROVAL gate authorizes exactly one external
    # action, once (python-only value; VARCHAR storage — no migration needed).
    EXTERNAL_ACTION_APPROVAL = "external_action_approval"


class ApprovalGateStatus(StrEnum):
    """Lifecycle status for an approval gate."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class MissionGraphRelation(StrEnum):
    """Semantics of an edge in the mission traceability graph."""

    DERIVED_FROM = "derived_from"
    DEPENDS_ON = "depends_on"
    ASSIGNED_TO = "assigned_to"
    EXECUTED_BY = "executed_by"
    MEASURED_BY = "measured_by"
    BLOCKED_BY = "blocked_by"
    GENERATED_BY = "generated_by"
    IMPROVES = "improves"
    TRIGGERS = "triggers"


class AutonomyLevel(StrEnum):
    """Per-company autonomy tier (governance, not trust)."""

    MANUAL = "manual"
    ASSISTED = "assisted"
    BOUNDED_AUTONOMY = "bounded_autonomy"
    HIGH_AUTONOMY = "high_autonomy"


# ── Mission ──────────────────────────────────────────────────────────────────


class Mission(Base):
    """A startup mission: why the company exists and where it is going.

    ``analysis`` and ``validation`` columns hold the deterministic/structured
    outputs produced by the MissionAnalyzer / MissionValidator — never private
    chain-of-thought, only distilled, auditable results.
    """

    __tablename__ = "missions"
    __table_args__ = (
        Index("ix_missions_company_status", "company_id", "status"),
        Index("ix_missions_owner", "owner_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mission_statement: Mapped[str] = mapped_column(Text, nullable=False)
    desired_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_market: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    strategic_context: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[MissionStatus] = mapped_column(
        _enum_column(MissionStatus, "mission_status"),
        nullable=False,
        default=MissionStatus.DRAFT,
    )
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    validation: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    startup_plans: Mapped[list[StartupPlan]] = relationship("StartupPlan", back_populates="mission")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Mission id={self.id} title={self.title!r} status={self.status.value}>"


# ── Strategic / startup planning ─────────────────────────────────────────────


class StrategicPlan(Base):
    """A strategic plan derived from a mission (vision + objectives + how)."""

    __tablename__ = "strategic_plans"
    __table_args__ = (Index("ix_strategic_plans_mission", "mission_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("missions.id", ondelete="CASCADE"), nullable=False
    )
    vision: Mapped[str | None] = mapped_column(Text, nullable=True)
    objectives: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    priorities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    expected_outcomes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    milestones: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    capabilities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    resource_estimates: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    success_metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    status: Mapped[StrategicPlanStatus] = mapped_column(
        _enum_column(StrategicPlanStatus, "strategic_plan_status"),
        nullable=False,
        default=StrategicPlanStatus.DRAFT,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StartupPlan(Base):
    """A concrete, approved plan to bootstrap and operate a startup company."""

    __tablename__ = "startup_plans"
    __table_args__ = (
        Index("ix_startup_plans_mission", "mission_id"),
        Index("ix_startup_plans_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("missions.id", ondelete="CASCADE"), nullable=False
    )
    mission: Mapped[Mission] = relationship("Mission", back_populates="startup_plans")
    strategic_plan_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("strategic_plans.id", ondelete="SET NULL"), nullable=True
    )
    business_objectives: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    product_objectives: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    market_objectives: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    organization_objectives: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    operational_objectives: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    milestones: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    departments: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    roles: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    capabilities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    initial_products: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    initial_projects: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    kpi_targets: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    budget_allocation: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    execution_priorities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    approval_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[StartupPlanStatus] = mapped_column(
        _enum_column(StartupPlanStatus, "startup_plan_status"),
        nullable=False,
        default=StartupPlanStatus.DRAFT,
    )
    review: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON validation review

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrganizationalBlueprint(Base):
    """A configurable organizational structure produced for a startup plan."""

    __tablename__ = "organizational_blueprints"
    __table_args__ = (Index("ix_blueprints_startup_plan", "startup_plan_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    startup_plan_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("startup_plans.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="Default blueprint")
    structure: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    # departments / roles / reporting / authority / skills / staffing /
    # objectives / kpis / budgets — all configurable, never hardcoded.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkforcePlan(Base):
    """Planned workforce demand (roles/skills/count/priority/workload/budget)."""

    __tablename__ = "workforce_plans"
    __table_args__ = (Index("ix_workforce_plans_startup_plan", "startup_plan_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    startup_plan_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("startup_plans.id", ondelete="CASCADE"), nullable=False
    )
    demand: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list of roles
    approval_policy: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Products / projects ──────────────────────────────────────────────────────


class Product(Base):
    """A product built and operated by the startup company."""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_company_status", "company_id", "status"),
        Index("ix_products_owner", "owner_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_users: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    value_proposition: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        _enum_column(ProductStatus, "product_status"),
        nullable=False,
        default=ProductStatus.IDEA,
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    strategic_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    budget: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    success_metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    launch_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    validation: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StartupProject(Base):
    """A startup project, optionally tied to a product, department, and goals."""

    __tablename__ = "startup_projects"
    __table_args__ = (
        Index("ix_startup_projects_company_status", "company_id", "status"),
        Index("ix_startup_projects_product", "product_id"),
        Index("ix_startup_projects_owner", "owner_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[StartupProjectStatus] = mapped_column(
        _enum_column(StartupProjectStatus, "startup_project_status"),
        nullable=False,
        default=StartupProjectStatus.PLANNED,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    budget: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    milestones: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Execution / operating cycle ──────────────────────────────────────────────


class ExecutionPlan(Base):
    """A coordinated set of goals/projects/employees/tasks to execute.

    ``tasks``/``workflows``/``orchestrations`` reference the Phase 1–8 entities
    by id (JSON list of ids + metadata); execution itself reuses TaskService,
    WorkflowService and OrchestrationService — no second execution engine.
    """

    __tablename__ = "execution_plans"
    __table_args__ = (
        Index("ix_execution_plans_company", "company_id"),
        Index("ix_execution_plans_mission", "mission_id"),
        Index("ix_execution_plans_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("missions.id", ondelete="CASCADE"), nullable=False
    )
    startup_plan_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("startup_plans.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    objective_scope: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    projects: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of ids
    employees: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of ids
    workflows: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of ids
    orchestrations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of ids
    tasks: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of ids
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    milestones: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    verification_policy: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    approval_gates: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    resource_limits: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[ExecutionPlanStatus] = mapped_column(
        _enum_column(ExecutionPlanStatus, "execution_plan_status"),
        nullable=False,
        default=ExecutionPlanStatus.DRAFT,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompanyStateSnapshot(Base):
    """An observed snapshot of company state at a point in time.

    ``overall_score`` and every dimension in ``dimensions`` must be backed by
    observable metrics computed server-side from authoritative data — never a
    fabricated number.
    """

    __tablename__ = "company_state_snapshots"
    __table_args__ = (Index("ix_snapshots_company_computed", "company_id", "computed_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    cycle_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("operating_cycles.id", ondelete="SET NULL"), nullable=True
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dimensions: Mapped[str] = mapped_column(Text, nullable=False)  # JSON dict
    explanations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OperatingCycle(Base):
    """One immutable operating cycle for a company.

    ``stages`` is an ordered, immutable timeline of the cycle stages already
    completed (never mutated after the row is written). ``decisions``,
    ``actions``, ``failures``, ``recovery``, ``approvals``, ``resource_usage``
    and ``outcome`` are JSON records of what the cycle actually did.
    """

    __tablename__ = "operating_cycles"
    __table_args__ = (
        Index("ix_operating_cycles_company_number", "company_id", "cycle_number"),
        Index("ix_operating_cycles_mission", "mission_id"),
        Index("ix_operating_cycles_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    mission_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True
    )
    startup_plan_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("startup_plans.id", ondelete="SET NULL"), nullable=True
    )
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[OperatingCycleStatus] = mapped_column(
        _enum_column(OperatingCycleStatus, "operating_cycle_status"),
        nullable=False,
        default=OperatingCycleStatus.INITIALIZING,
    )
    stages: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list (immutable)
    state_snapshot_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("company_state_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    decisions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    actions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    kpis: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    failures: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    recovery: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    approvals: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    resource_usage: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Feedback / lessons ───────────────────────────────────────────────────────


class StartupFeedback(Base):
    """Structured feedback surfaced to a human — never auto-executed."""

    __tablename__ = "startup_feedback"
    __table_args__ = (
        Index("ix_startup_feedback_company_created", "company_id", "created_at"),
        Index("ix_startup_feedback_mission", "mission_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    mission_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True
    )
    objective_type: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)  # non-executing
    related_goal_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    related_project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    related_product_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StartupLesson(Base):
    """A recorded lesson, mirrored into the Phase 4 memory system."""

    __tablename__ = "startup_lessons"
    __table_args__ = (
        Index("ix_startup_lessons_company_created", "company_id", "created_at"),
        Index("ix_startup_lessons_mission", "mission_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    mission_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True
    )
    lesson_type: Mapped[LessonType] = mapped_column(
        _enum_column(LessonType, "startup_lesson_type"),
        nullable=False,
        default=LessonType.LESSON,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Governance / autonomy ────────────────────────────────────────────────────


class ApprovalGate(Base):
    """A human decision point required before a high-impact autonomous action."""

    __tablename__ = "approval_gates"
    __table_args__ = (
        Index("ix_approval_gates_company_status", "company_id", "status"),
        Index("ix_approval_gates_requester", "requester_id"),
        Index("ix_approval_gates_approver", "approver_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    gate_type: Mapped[ApprovalGateType] = mapped_column(
        _enum_column(ApprovalGateType, "approval_gate_type"),
        nullable=False,
    )
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    requested_action: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_entities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    resource_impact: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    requester_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    approver_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ApprovalGateStatus] = mapped_column(
        _enum_column(ApprovalGateStatus, "approval_gate_status"),
        nullable=False,
        default=ApprovalGateStatus.PENDING,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AutonomyPolicy(Base):
    """Per-company autonomy governance (one policy per company)."""

    __tablename__ = "autonomy_policies"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_autonomy_policies_company"),
        Index("ix_autonomy_policies_level", "autonomy_level"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    autonomy_level: Mapped[AutonomyLevel] = mapped_column(
        _enum_column(AutonomyLevel, "autonomy_level"),
        nullable=False,
        default=AutonomyLevel.BOUNDED_AUTONOMY,
    )
    allow_matrix: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON
    max_employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_departments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_concurrent_work: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_provisioning_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    require_approval_for: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )  # JSON list

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Traceability / resource / priority decisions ─────────────────────────────


class MissionGraphEdge(Base):
    """A directed edge in the mission traceability graph."""

    __tablename__ = "mission_graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relation",
            name="uq_mission_graph_edge",
        ),
        Index("ix_mission_graph_source", "source_type", "source_id"),
        Index("ix_mission_graph_target", "target_type", "target_id"),
        Index("ix_mission_graph_company", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    relation: Mapped[MissionGraphRelation] = mapped_column(
        _enum_column(MissionGraphRelation, "mission_graph_relation"),
        nullable=False,
    )
    edge_metadata: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ResourceAllocation(Base):
    """A recorded resource allocation (budget/capacity/tokens/tools/time)."""

    __tablename__ = "resource_allocations"
    __table_args__ = (
        Index("ix_resource_allocations_company", "company_id"),
        Index("ix_resource_allocations_target", "target_type", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PriorityDecision(Base):
    """A recorded, explainable priority decision made by the PriorityEngine."""

    __tablename__ = "priority_decisions"
    __table_args__ = (
        Index("ix_priority_decisions_company", "company_id"),
        Index("ix_priority_decisions_target", "target_type", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    score: Mapped[str] = mapped_column(Text, nullable=False)  # JSON (float or dict)
    factors: Mapped[str] = mapped_column(Text, nullable=False)  # JSON dict
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
