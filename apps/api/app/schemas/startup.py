"""Pydantic API schemas for the Autonomous Startup Engine (Phase 9).

Mirror the ORM models in :mod:`app.db.models.startup` while staying decoupled
from SQLAlchemy (matching ``company.py`` / ``task.py``). Read schemas serialize
the same shapes the startup services produce in their ``to_dict`` methods;
Create/Update schemas accept the payloads those services consume. Rich JSON
payloads (analysis, plans, criteria, matrices, verdicts) are typed as ``Any``
and round-tripped by the services.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.startup import (
    ApprovalGateStatus,
    ApprovalGateType,
    AutonomyLevel,
    ExecutionPlanStatus,
    LessonType,
    MissionGraphRelation,
    MissionStatus,
    OperatingCycleStatus,
    ProductStatus,
    StartupPlanStatus,
    StartupProjectStatus,
    StrategicPlanStatus,
)

# ── Mission ─────────────────────────────────────────────────────────────


class MissionCreate(BaseModel):
    """Payload to create a startup mission."""

    company_id: UUID
    title: str = Field(min_length=1, max_length=256)
    description: str | None = None
    mission_statement: str = Field(min_length=1)
    desired_outcome: str | None = None
    target_market: str | None = None
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    strategic_context: dict[str, Any] | None = None
    priority: int = 0
    owner_id: UUID | None = None


class MissionUpdate(BaseModel):
    """Partial update payload for a mission."""

    title: str | None = None
    description: str | None = None
    mission_statement: str | None = None
    desired_outcome: str | None = None
    target_market: str | None = None
    constraints: list[str] | None = None
    assumptions: list[str] | None = None
    success_criteria: list[str] | None = None
    strategic_context: dict[str, Any] | None = None
    priority: int | None = None
    owner_id: UUID | None = None


class MissionRead(BaseModel):
    """Full mission representation returned by the API."""

    id: UUID
    company_id: UUID
    title: str
    description: str | None = None
    mission_statement: str
    desired_outcome: str | None = None
    target_market: str | None = None
    constraints: Any = None
    assumptions: Any = None
    success_criteria: Any = None
    strategic_context: Any = None
    priority: int
    status: MissionStatus
    analysis: Any = None
    validation: Any = None
    owner_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MissionAnalysisResultRead(BaseModel):
    """Structured mission analysis output."""

    objectives: list[str] = Field(default_factory=list)
    target_market: str | None = None
    problem: str | None = None
    proposed_solution: str | None = None
    constraints: list[str] = Field(default_factory=list)
    timeline: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    analyzer: str = "deterministic"


class ValidationIssueRead(BaseModel):
    """A single validation finding."""

    code: str
    message: str
    severity: str = "error"


class ValidationResultRead(BaseModel):
    """Aggregate validation outcome."""

    ok: bool
    errors: list[ValidationIssueRead] = Field(default_factory=list)
    warnings: list[ValidationIssueRead] = Field(default_factory=list)


# ── Strategic / startup plans ───────────────────────────────────────────


class StrategicPlanCreate(BaseModel):
    """Payload/structure for a strategic plan (vision + objectives + how)."""

    vision: str | None = None
    objectives: list[Any] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    milestones: list[Any] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    resource_estimates: dict[str, Any] = Field(default_factory=dict)
    success_metrics: list[str] = Field(default_factory=list)
    status: StrategicPlanStatus = StrategicPlanStatus.DRAFT


class StrategicPlanRead(BaseModel):
    """Strategic plan representation."""

    id: UUID
    mission_id: UUID
    vision: str | None = None
    objectives: Any = None
    priorities: Any = None
    expected_outcomes: Any = None
    assumptions: Any = None
    risks: Any = None
    milestones: Any = None
    dependencies: Any = None
    capabilities: Any = None
    resource_estimates: Any = None
    success_metrics: Any = None
    status: StrategicPlanStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class StartupPlanCreate(BaseModel):
    """Payload to create a startup plan for a mission."""

    mission_id: UUID
    strategic_plan_id: UUID | None = None
    business_objectives: list[Any] = Field(default_factory=list)
    product_objectives: list[Any] = Field(default_factory=list)
    market_objectives: list[Any] = Field(default_factory=list)
    organization_objectives: list[Any] = Field(default_factory=list)
    operational_objectives: list[Any] = Field(default_factory=list)
    milestones: list[Any] = Field(default_factory=list)
    departments: list[Any] = Field(default_factory=list)
    roles: list[Any] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    initial_products: list[dict[str, Any]] = Field(default_factory=list)
    initial_projects: list[dict[str, Any]] = Field(default_factory=list)
    kpi_targets: dict[str, Any] = Field(default_factory=dict)
    budget_allocation: dict[str, Any] = Field(default_factory=dict)
    execution_priorities: list[str] = Field(default_factory=list)
    approval_requirements: list[Any] = Field(default_factory=list)


class StartupPlanUpdate(BaseModel):
    """Partial update payload for a startup plan."""

    strategic_plan_id: UUID | None = None
    business_objectives: list[Any] | None = None
    product_objectives: list[Any] | None = None
    market_objectives: list[Any] | None = None
    organization_objectives: list[Any] | None = None
    operational_objectives: list[Any] | None = None
    milestones: list[Any] | None = None
    departments: list[Any] | None = None
    roles: list[Any] | None = None
    capabilities: list[str] | None = None
    initial_products: list[dict[str, Any]] | None = None
    initial_projects: list[dict[str, Any]] | None = None
    kpi_targets: dict[str, Any] | None = None
    budget_allocation: dict[str, Any] | None = None
    execution_priorities: list[str] | None = None
    approval_requirements: list[Any] | None = None


class StartupPlanRead(BaseModel):
    """Startup plan representation."""

    id: UUID
    mission_id: UUID
    strategic_plan_id: UUID | None = None
    business_objectives: Any = None
    product_objectives: Any = None
    market_objectives: Any = None
    organization_objectives: Any = None
    operational_objectives: Any = None
    milestones: Any = None
    departments: Any = None
    roles: Any = None
    capabilities: Any = None
    initial_products: Any = None
    initial_projects: Any = None
    kpi_targets: Any = None
    budget_allocation: Any = None
    execution_priorities: Any = None
    approval_requirements: Any = None
    status: StartupPlanStatus
    review: Any = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Blueprint / workforce ───────────────────────────────────────────────


class BlueprintRead(BaseModel):
    """Organizational blueprint representation."""

    id: UUID
    startup_plan_id: UUID
    name: str
    structure: Any = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkforcePlanRead(BaseModel):
    """Workforce plan representation."""

    id: UUID
    startup_plan_id: UUID
    demand: Any = None
    approval_policy: Any = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Products / projects ─────────────────────────────────────────────────


class ProductCreate(BaseModel):
    """Payload to create a product."""

    company_id: UUID
    name: str = Field(min_length=1, max_length=256)
    description: str | None = None
    product_type: str | None = None
    target_users: list[str] = Field(default_factory=list)
    value_proposition: str | None = None
    owner_id: UUID | None = None
    strategic_priority: int = 0
    budget: dict[str, Any] | None = None
    success_metrics: list[str] = Field(default_factory=list)
    launch_criteria: list[str] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    """Partial update payload for a product."""

    name: str | None = None
    description: str | None = None
    product_type: str | None = None
    target_users: list[str] | None = None
    value_proposition: str | None = None
    owner_id: UUID | None = None
    strategic_priority: int | None = None
    budget: dict[str, Any] | None = None
    success_metrics: list[str] | None = None
    launch_criteria: list[str] | None = None


class ProductRead(BaseModel):
    """Full product representation."""

    id: UUID
    company_id: UUID
    name: str
    description: str | None = None
    product_type: str | None = None
    target_users: Any = None
    value_proposition: str | None = None
    status: ProductStatus
    owner_id: UUID | None = None
    strategic_priority: int
    budget: Any = None
    success_metrics: Any = None
    launch_criteria: Any = None
    validation: Any = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductLifecycleMove(BaseModel):
    """Payload to move a product through its lifecycle."""

    target: ProductStatus


class ProjectCreate(BaseModel):
    """Payload to create a startup project."""

    company_id: UUID
    name: str = Field(min_length=1, max_length=256)
    description: str | None = None
    objective: str | None = None
    product_id: UUID | None = None
    department_id: UUID | None = None
    owner_id: UUID | None = None
    status: StartupProjectStatus = StartupProjectStatus.PLANNED
    priority: int = 0
    budget: dict[str, Any] | None = None
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    start_date: datetime | None = None
    deadline: datetime | None = None
    goal_id: UUID | None = None


class ProjectUpdate(BaseModel):
    """Partial update payload for a startup project."""

    name: str | None = None
    description: str | None = None
    objective: str | None = None
    product_id: UUID | None = None
    department_id: UUID | None = None
    owner_id: UUID | None = None
    priority: int | None = None
    budget: dict[str, Any] | None = None
    milestones: list[dict[str, Any]] | None = None
    dependencies: list[dict[str, Any]] | None = None
    success_criteria: list[str] | None = None
    start_date: datetime | None = None
    deadline: datetime | None = None


class ProjectRead(BaseModel):
    """Full startup project representation."""

    id: UUID
    company_id: UUID
    product_id: UUID | None = None
    department_id: UUID | None = None
    name: str
    description: str | None = None
    objective: str | None = None
    owner_id: UUID | None = None
    status: StartupProjectStatus
    priority: int
    budget: Any = None
    milestones: Any = None
    dependencies: Any = None
    success_criteria: Any = None
    start_date: datetime | None = None
    deadline: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectLifecycleMove(BaseModel):
    """Payload to move a project through its lifecycle."""

    target: StartupProjectStatus


# ── Execution plans / operating cycles ──────────────────────────────────


class ExecutionPlanRead(BaseModel):
    """Execution plan representation (snapshot of referenced work)."""

    id: UUID
    company_id: UUID
    mission_id: UUID
    startup_plan_id: UUID | None = None
    objective_scope: Any = None
    projects: Any = None
    employees: Any = None
    tasks: Any = None
    workflows: Any = None
    orchestrations: Any = None
    verification_policy: Any = None
    resource_limits: Any = None
    status: ExecutionPlanStatus
    created_at: datetime | None = None


class CycleCreate(BaseModel):
    """Payload to start an operating cycle."""

    mission_id: UUID
    startup_plan_id: UUID | None = None
    approved_gate_id: UUID | None = None


class CycleRead(BaseModel):
    """Immutable operating cycle representation."""

    id: UUID
    company_id: UUID
    mission_id: UUID | None = None
    startup_plan_id: UUID | None = None
    cycle_number: int
    status: OperatingCycleStatus
    stages: list[dict[str, Any]] = Field(default_factory=list)
    state_snapshot_id: UUID | None = None
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    kpis: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    recovery: list[dict[str, Any]] = Field(default_factory=list)
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    resource_usage: Any = None
    outcome: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class CycleDecisionBody(BaseModel):
    """Body for a cycle resume/decision action."""

    approved_gate_id: UUID | None = None
    note: str | None = None


class CompanyStateSnapshotRead(BaseModel):
    """Observed company state snapshot."""

    id: UUID
    company_id: UUID
    cycle_id: UUID | None = None
    overall_score: float
    dimensions: dict[str, float] = Field(default_factory=dict)
    explanations: dict[str, str] = Field(default_factory=dict)
    computed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Feedback / lessons ──────────────────────────────────────────────────


class FeedbackCreate(BaseModel):
    """Payload to record a structured feedback signal."""

    category: str = Field(min_length=1, max_length=64)
    observation: str = Field(min_length=1)
    mission_id: UUID | None = None
    source: str | None = None
    impact: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    recommendation: str | None = None
    objective_type: dict[str, Any] | None = None
    related_goal_id: UUID | None = None
    related_project_id: UUID | None = None
    related_product_id: UUID | None = None


class FeedbackRead(BaseModel):
    """Feedback record representation."""

    id: UUID
    company_id: UUID
    mission_id: UUID | None = None
    objective_type: Any = None
    source: str | None = None
    category: str
    observation: str
    impact: str | None = None
    confidence: float
    recommendation: str | None = None
    related_goal_id: UUID | None = None
    related_project_id: UUID | None = None
    related_product_id: UUID | None = None
    created_at: datetime | None = None


class LessonRead(BaseModel):
    """Lesson record representation."""

    id: UUID
    company_id: UUID
    mission_id: UUID | None = None
    lesson_type: LessonType
    title: str  # noqa: E501
    content: str
    source: Any = None
    created_at: datetime | None = None


# ── Governance / autonomy ───────────────────────────────────────────────


class ApprovalGateRead(BaseModel):
    """Human approval gate representation."""

    id: UUID
    company_id: UUID
    gate_type: ApprovalGateType
    risk_level: str
    requested_action: Any = None
    rationale: str | None = None
    affected_entities: Any = None
    resource_impact: Any = None
    requester_id: UUID | None = None
    approver_id: UUID | None = None
    status: ApprovalGateStatus
    decided_at: datetime | None = None
    expiration: datetime | None = None
    created_at: datetime | None = None


class ApprovalDecisionBody(BaseModel):
    """Body for approving/rejecting an approval gate."""

    approver_id: UUID | None = None
    rationale: str | None = None


class AutonomyPolicyRead(BaseModel):
    """Per-company autonomy governance policy."""

    company_id: UUID
    autonomy_level: AutonomyLevel
    allow_matrix: dict[str, str] = Field(default_factory=dict)
    never_allowed: list[str] = Field(default_factory=list)
    max_employees: int | None = None
    max_departments: int | None = None
    max_budget: float | None = None
    max_concurrent_work: int | None = None
    max_provisioning_rate: int | None = None
    require_approval_for: list[str] = Field(default_factory=list)


class AutonomyPolicyUpdate(BaseModel):
    """Partial update payload for an autonomy policy.

    Changing ``autonomy_level`` is ``change_autonomy`` — never automatic. The
    caller is expected to supply an approved gate id when raising autonomy.
    """

    autonomy_level: AutonomyLevel | None = None
    allow_matrix: dict[str, str] | None = None
    max_employees: int | None = None
    max_departments: int | None = None
    max_budget: float | None = None
    max_concurrent_work: int | None = None
    max_provisioning_rate: int | None = None
    require_approval_for: list[str] | None = None
    approved_gate_id: UUID | None = None


# ── Traceability / resources / priorities ───────────────────────────────


class MissionGraphEdgeRead(BaseModel):
    """A directed edge in the mission traceability graph."""

    id: UUID
    company_id: UUID
    source_type: str
    source_id: UUID
    target_type: str
    target_id: UUID
    relation: MissionGraphRelation
    metadata: Any = None
    created_at: datetime | None = None


class MissionGraphRead(BaseModel):
    """A queryable view of a company's mission graph."""

    edges: list[MissionGraphEdgeRead] = Field(default_factory=list)
    total: int = 0


class TraceRead(BaseModel):
    """Trace of *why a node exists* — walked back to the mission."""

    origin: dict[str, Any]
    chain: list[dict[str, Any]] = Field(default_factory=list)
    reached_mission: bool = False


class ResourceAllocationRead(BaseModel):
    """Resource allocation representation."""

    id: UUID
    company_id: UUID
    target_type: str
    target_id: UUID
    resource_type: str
    amount: float
    unit: str | None = None
    purpose: Any = None
    actor: str
    created_at: datetime | None = None


class PriorityDecisionRead(BaseModel):
    """Prioritization decision representation."""

    id: UUID
    company_id: UUID
    target_type: str
    target_id: UUID
    score: Any = None
    factors: Any = None
    reason: str | None = None
    created_at: datetime | None = None


class PriorityScoreRead(BaseModel):
    """Result of scoring a target by weighted factors."""

    target_type: str
    target_id: UUID
    score: float
    factors: dict[str, float] = Field(default_factory=dict)
    reason: str = ""


class ReplanDecisionRead(BaseModel):
    """The ReplanningEngine's chosen bounded response."""

    trigger: str
    response: str
    reason: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    requires_approval: bool = False


class ReplanActionRead(BaseModel):
    """Result of applying a replanning decision."""

    decision: ReplanDecisionRead
    applied: list[dict[str, Any]] = Field(default_factory=list)
