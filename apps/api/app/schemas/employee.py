"""Pydantic API schemas for AI Employee OS (Phase 7).

Mirror the ORM models in :mod:`app.db.models.employee` but stay decoupled
from SQLAlchemy so they can validate API input and serialize API output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.employee import EmployeeAvailability, EmployeeStatus, GoalStatus

# ── Employee ──────────────────────────────────────────────────────────────────


class EmployeeCreate(BaseModel):
    """Payload to create a new AI employee."""

    name: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)
    description: str | None = None
    role: str = Field(default="general", max_length=64)
    department: str | None = Field(default=None, max_length=64)
    agent_id: UUID | None = None
    skills: list[dict[str, Any]] | None = None
    responsibilities: list[str] | None = None
    tools: list[str] | None = None
    permissions: list[str] | None = None
    policies: dict[str, Any] | None = None
    workload_config: dict[str, Any] | None = None


class EmployeeUpdate(BaseModel):
    """Partial update payload for an AI employee."""

    display_name: str | None = None
    description: str | None = None
    role: str | None = None
    department: str | None = None
    agent_id: UUID | None = None
    skills: list[dict[str, Any]] | None = None
    responsibilities: list[str] | None = None
    tools: list[str] | None = None
    permissions: list[str] | None = None
    policies: dict[str, Any] | None = None
    workload_config: dict[str, Any] | None = None


class EmployeeRead(BaseModel):
    """Full employee representation returned by the API."""

    id: UUID
    name: str
    display_name: str | None = None
    description: str | None = None
    role: str
    department: str | None = None
    status: EmployeeStatus
    availability: EmployeeAvailability
    agent_id: UUID | None = None
    skills: list[dict[str, Any]] | None = None
    responsibilities: list[str] | None = None
    goals: list[str] | None = None
    tools: list[str] | None = None
    permissions: list[str] | None = None
    memory_namespace: str | None = None
    work_preferences: dict[str, Any] | None = None
    workload_config: dict[str, Any] | None = None
    performance_profile: dict[str, Any] | None = None
    policies: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeeList(BaseModel):
    """Paginated list of employees."""

    items: list[EmployeeRead]
    total: int


# ── Goal ──────────────────────────────────────────────────────────────────────


class GoalCreate(BaseModel):
    """Payload to create a goal for an employee."""

    title: str = Field(min_length=1, max_length=256)
    description: str | None = None
    priority: int = 0
    target: str | None = None
    metric: str | None = None


class GoalUpdate(BaseModel):
    """Partial update payload for a goal."""

    title: str | None = None
    description: str | None = None
    priority: int | None = None
    target: str | None = None
    metric: str | None = None
    status: GoalStatus | None = None
    progress: float | None = None


class GoalRead(BaseModel):
    """Goal representation returned by the API."""

    id: UUID
    employee_id: UUID
    title: str
    description: str | None = None
    priority: int
    target: str | None = None
    metric: str | None = None
    deadline: datetime | None = None
    status: GoalStatus
    progress: float
    parent_goal_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Budget ────────────────────────────────────────────────────────────────────


class BudgetRead(BaseModel):
    """Budget representation returned by the API."""

    id: UUID
    employee_id: UUID
    monthly_limit: float
    task_limit: float | None = None
    tokens_used: int
    cost_used: float
    tool_calls_used: int
    period_start: datetime
    period_end: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Review ────────────────────────────────────────────────────────────────────


class ReviewRead(BaseModel):
    """Performance review representation."""

    id: UUID
    employee_id: UUID
    period_start: datetime
    period_end: datetime | None = None
    metrics: dict[str, Any] | None = None
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    skill_changes: list[str] | None = None
    recommendations: list[str] | None = None
    reviewer: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Template ──────────────────────────────────────────────────────────────────


class TemplateCreate(BaseModel):
    """Payload to create a template."""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    role: str = Field(default="general", max_length=64)
    skills: list[dict[str, Any]] | None = None
    responsibilities: list[str] | None = None
    tools: list[str] | None = None
    policies: dict[str, Any] | None = None
    verification_policy: dict[str, Any] | None = None


class TemplateRead(BaseModel):
    """Template representation."""

    id: UUID
    name: str
    description: str | None = None
    role: str
    skills: list[dict[str, Any]] | None = None
    responsibilities: list[str] | None = None
    tools: list[str] | None = None
    policies: dict[str, Any] | None = None
    verification_policy: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TemplateList(BaseModel):
    """List of templates."""

    items: list[TemplateRead]
    total: int


class CreateFromTemplateRequest(BaseModel):
    """Payload to create an employee from a template."""

    name: str = Field(min_length=1, max_length=128)
    display_name: str | None = None
    agent_id: UUID | None = None
    overrides: dict[str, Any] | None = None


# ── Workload / Performance ───────────────────────────────────────────────────


class WorkloadRead(BaseModel):
    """Workload snapshot."""

    employee_id: UUID
    active_tasks: int = 0
    queued_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    capacity: int = 5
    utilization: float = 0.0
    available_slots: int = 5


class PerformanceRead(BaseModel):
    """Performance metrics."""

    employee_id: UUID
    tasks_completed: int = 0
    tasks_failed: int = 0
    success_rate: float = 0.0
    verification_pass_rate: float = 0.0
    average_quality: float = 0.0
    recovery_rate: float = 0.0
    average_latency_ms: float = 0.0
    total_cost: float = 0.0
    total_tokens: int = 0
    utilization: float = 0.0
    deadline_adherence: float = 0.0
    period_start: datetime | None = None
    period_end: datetime | None = None


# ── Timeline / Audit ─────────────────────────────────────────────────────────


class TimelineEvent(BaseModel):
    """A single timeline event."""

    event_id: UUID
    employee_id: UUID | None = None
    event_type: str
    description: str
    timestamp: str | None = None
    outcome: str | None = None


class AuditEntry(BaseModel):
    """A single audit log entry."""

    id: UUID
    actor: str
    action: str
    target_type: str | None = None
    target_id: UUID | None = None
    details: dict[str, Any] | None = None
    outcome: str | None = None
    created_at: str | None = None


# ── Assignment ────────────────────────────────────────────────────────────────


class AssignmentRequestSchema(BaseModel):
    """Payload to request task assignment."""

    task_id: UUID | None = None
    task_title: str = ""
    task_description: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_role: str | None = None
    priority: int = 0


class AssignmentResultSchema(BaseModel):
    """Assignment result."""

    success: bool
    employee_id: UUID | None = None
    employee_name: str | None = None
    task_id: UUID | None = None
    score: float = 0.0
    reasoning: str = ""
    candidates_evaluated: int = 0


# ── Workforce ─────────────────────────────────────────────────────────────────


class WorkforceOverview(BaseModel):
    """Aggregate workforce statistics."""

    total_employees: int
    active_employees: int
    by_status: dict[str, int]
