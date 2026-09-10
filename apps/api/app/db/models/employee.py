"""AI Employee domain models (Phase 7).

Persistent organizational entities wrapping agents with identity, role, skills,
responsibilities, goals, policies, budgets, and performance tracking.

Design notes (mirroring project convention):
- Structured fields (skills, responsibilities, goals, policies) are stored as
  JSON Text blobs so the relational columns carry identity/lifecycle/state.
- Enum columns use the project's ``_enum_values`` / ``native_enum=False`` /
  ``create_constraint=False`` convention.
- Foreign keys use ``ondelete="CASCADE"`` where a child is meaningless without
  its parent.
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


# ── Tables ────────────────────────────────────────────────────────────────────


class AIEmployee(Base):
    """A persistent organizational entity wrapping an agent.

    The employee carries identity, role, skills, responsibilities, goals,
    tools, permissions, policies, and performance metadata.  It references an
    existing Agent for execution but does NOT duplicate agent execution state.

    JSON blobs:
        skills: ``[{skill_id, name, category, proficiency, confidence, ...}]``
        responsibilities: ``["conduct market research", ...]``
        goals: ``["goal_id", ...]`` (references ``employee_goals``)
        tools: ``["tool_name", ...]``
        permissions: ``["scope:action", ...]``
        work_preferences: ``{}``
        workload_config: ``{max_concurrent, capacity}``
        performance_profile: ``{}``
        policies: ``{max_concurrent_tasks, requires_verification, ...}``
    """

    __tablename__ = "ai_employees"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[EmployeeStatus] = mapped_column(
        _enum_column(EmployeeStatus, "employee_status"),
        nullable=False,
        default=EmployeeStatus.DRAFT,
    )
    availability: Mapped[EmployeeAvailability] = mapped_column(
        _enum_column(EmployeeAvailability, "employee_availability"),
        nullable=False,
        default=EmployeeAvailability.UNAVAILABLE,
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Structured JSON fields
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of goal IDs
    tools: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    permissions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    memory_namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    work_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    workload_config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    performance_profile: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    policies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_ai_employees_status", "status"),
        Index("ix_ai_employees_role", "role"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AIEmployee id={self.id} name={self.name!r} status={self.status.value}>"


class EmployeeGoal(Base):
    """An individual goal assigned to an AI employee."""

    __tablename__ = "employee_goals"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metric: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[GoalStatus] = mapped_column(
        _enum_column(GoalStatus, "goal_status"),
        nullable=False,
        default=GoalStatus.NOT_STARTED,
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    parent_goal_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_employee_goals_emp_status", "employee_id", "status"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EmployeeGoal id={self.id} title={self.title!r} status={self.status.value}>"


class EmployeeBudget(Base):
    """Per-employee resource tracking (tokens, cost, tool calls)."""

    __tablename__ = "employee_budgets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_employees.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    monthly_limit: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    task_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_used: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tool_calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EmployeeBudget id={self.id} employee={self.employee_id}>"


class EmployeeReview(Base):
    """A performance review for an AI employee."""

    __tablename__ = "employee_reviews"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    weaknesses: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    skill_changes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    reviewer: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_employee_reviews_emp_created", "employee_id", "created_at"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EmployeeReview id={self.id} employee={self.employee_id}>"


class EmployeeTemplate(Base):
    """A reusable template for creating AI employees with pre-configured settings."""

    __tablename__ = "employee_templates"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    tools: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    policies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    verification_policy: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EmployeeTemplate id={self.id} name={self.name!r}>"


class EmployeeAuditLog(Base):
    """An immutable audit trail for important employee operations."""

    __tablename__ = "employee_audit_log"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_employee_audit_emp_created", "employee_id", "created_at"),
        Index("ix_employee_audit_action", "action"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EmployeeAuditLog id={self.id} action={self.action!r}>"
