"""AI Company Layer — domain types.

Plain dataclasses/type aliases used across the company services. Kept
decoupled from SQLAlchemy and Pydantic so services can build/return structured
results (policy resolutions, KPI snapshots, budget snapshots, org-chart nodes,
health snapshots) without leaking ORM objects to routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class PolicyResolution:
    """The resolved effective policy for a key across the hierarchy."""

    key: str
    value: Any
    source_scope: str  # "system" | "company" | "department" | "employee" | "task"
    source_name: str | None = None
    applicable_scopes: list[str] = field(default_factory=list)


@dataclass
class KpiSnapshot:
    """A computed KPI reading with trend + scope context."""

    kpi_id: UUID
    company_id: UUID
    scope_type: str
    scope_id: UUID
    name: str
    category: str
    source_metric: str
    value: float
    target: float | None = None
    variance: float | None = None
    trend: str | None = None
    unit: str | None = None
    owner_id: UUID | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BudgetSnapshot:
    """A budget accounting snapshot for company/department/employee scope."""

    company_id: UUID
    scope_type: str
    scope_id: UUID
    monthly_limit: float = 0.0
    allocated: float = 0.0
    reserved: float = 0.0
    spent: float = 0.0
    tokens_used: int = 0
    cost_used: float = 0.0
    tool_calls_used: int = 0
    execution_count: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None

    @property
    def remaining(self) -> float:
        return max(0.0, self.monthly_limit - self.spent - self.reserved)

    @property
    def utilization(self) -> float:
        if not self.monthly_limit:
            return 0.0
        return round((self.spent / self.monthly_limit) * 100.0, 2)


@dataclass
class OrgChartNode:
    """A node in the data-driven organization chart."""

    id: UUID
    type: str  # "company" | "department" | "employee"
    name: str
    role: str | None = None
    status: str | None = None
    manager_id: UUID | None = None
    children: list[OrgChartNode] = field(default_factory=list)


@dataclass
class OrgChart:
    """The full organization chart for a company."""

    company_id: UUID
    company_name: str
    root: OrgChartNode
    departments: int = 0
    employees: int = 0
    managers: int = 0


@dataclass
class DelegationRequest:
    """A request to delegate work down the organizational hierarchy."""

    company_id: UUID
    delegated_task: str
    delegator_employee_id: UUID
    target_employee_id: UUID
    department_id: UUID | None = None
    required_skills: list[str] = field(default_factory=list)
    priority: int = 0


@dataclass
class DelegationResult:
    """Outcome of a delegation attempt, with full explainability."""

    success: bool
    reasoning: str = ""
    task_id: UUID | None = None
    delegator_id: UUID | None = None
    target_id: UUID | None = None
    authority_verified: bool = False
    capability_verified: bool = False
    budget_verified: bool = False
    policy_verified: bool = False


@dataclass
class HealthScore:
    """A company-health dimension score exposing its underlying metrics."""

    dimension: str
    score: float
    metrics: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""


@dataclass
class CompanyHealthSnapshot:
    """Transparent company-health aggregation across dimensions."""

    company_id: UUID
    dimensions: list[HealthScore] = field(default_factory=list)

    @property
    def overall(self) -> float:
        if not self.dimensions:
            return 0.0
        return round(sum(d.score for d in self.dimensions) / len(self.dimensions), 1)


@dataclass
class OrganizationalReport:
    """A generated organizational report (recommendations non-executing)."""

    company_id: UUID
    report_type: str
    period_start: datetime
    period_end: datetime
    metrics: dict[str, Any]
    highlights: list[str]
    risks: list[dict[str, Any]]
    blockers: list[str]
    goal_progress: dict[str, Any]
    recommendations: list[str]
    evidence: dict[str, Any]
    verification_status: str = "unverified"
    verification_summary: str | None = None
