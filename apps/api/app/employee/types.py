"""AI Employee OS — domain types and dataclasses.

These are pure-Python value objects for business logic.  They are **not**
DB models (those live in ``app.db.models.employee``) and not Pydantic schemas
(those live in ``app.schemas.employee``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

# ── Enums (mirror DB enums for domain logic) ──────────────────────────────────


class EmployeeStatus(StrEnum):
    """Lifecycle status for an AI employee."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    BUSY = "busy"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class EmployeeAvailability(StrEnum):
    """Whether an employee can accept new work."""

    AVAILABLE = "available"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    PAUSED = "paused"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class GoalStatus(StrEnum):
    """Lifecycle status for an employee goal."""

    NOT_STARTED = "not_started"
    ACTIVE = "active"
    AT_RISK = "at_risk"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class SkillEntry:
    """A single skill attached to an employee."""

    skill_id: str
    name: str
    category: str = "general"
    proficiency: float = 0.5  # 0.0 – 1.0
    confidence: float = 0.5
    evidence_count: int = 0
    last_used: datetime | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class Responsibility:
    """A responsibility assigned to an employee."""

    description: str
    priority: int = 0
    active: bool = True


@dataclass
class EmployeePolicy:
    """Policies governing employee behaviour."""

    max_concurrent_tasks: int = 5
    requires_verification: bool = True
    max_retries: int = 2
    budget_limit: float = 50.0
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    working_hours: dict[str, Any] = field(default_factory=dict)
    escalation_policy: str = "auto"
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkloadSnapshot:
    """Point-in-time view of an employee's workload."""

    employee_id: UUID
    active_tasks: int = 0
    queued_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    capacity: int = 5
    utilization: float = 0.0  # 0.0 – 1.0
    available_slots: int = 5


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics for an employee."""

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


@dataclass
class AssignmentRequest:
    """A request to assign a task to an employee."""

    task_id: UUID | None = None
    task_title: str = ""
    task_description: str = ""
    required_skills: list[str] = field(default_factory=list)
    preferred_role: str | None = None
    priority: int = 0
    deadline: datetime | None = None
    input_data: dict[str, Any] = field(default_factory=dict)
    correlation_id: UUID = field(default_factory=uuid4)


@dataclass
class AssignmentResult:
    """Result of an assignment attempt."""

    success: bool
    employee_id: UUID | None = None
    employee_name: str | None = None
    task_id: UUID | None = None  # Set when the assignment persisted a real Task
    score: float = 0.0
    reasoning: str = ""
    candidates_evaluated: int = 0
    rejection_reasons: dict[UUID, str] = field(default_factory=dict)
    correlation_id: UUID = field(default_factory=uuid4)


@dataclass
class EmployeeTimelineEvent:
    """A single event in an employee's activity timeline."""

    event_id: UUID = field(default_factory=uuid4)
    employee_id: UUID | None = None
    event_type: str = ""
    description: str = ""
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
