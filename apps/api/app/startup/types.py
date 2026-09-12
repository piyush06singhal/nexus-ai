"""Autonomous Startup Engine — domain data types.

Plain dataclasses (and str-enums for closed sets) used between the startup
services. They are deliberately transport-neutral: the API layer converts them
to Pydantic schemas, the services pass them around internally. Keeping them as
dataclasses means the deterministic planners/analyzers are trivially testable
without an ORM or a model provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class ActionDecision(StrEnum):
    """How an autonomous action is governed."""

    ALLOW = "allow"  # may run automatically
    REQUIRE_APPROVAL = "require_approval"  # must pass a human approval gate
    BLOCK = "block"  # never autonomous; refused outright


class ReplanResponse(StrEnum):
    """A bounded response the ReplanningEngine may choose."""

    CONTINUE = "continue"
    REPRIORITIZE = "reprioritize"
    REASSIGN = "reassign"
    REPLAN = "replan"
    REDUCE_SCOPE = "reduce_scope"
    INCREASE_SCOPE = "increase_scope"
    PAUSE_PROJECT = "pause_project"
    ABORT_PROJECT = "abort_project"
    CREATE_NEW_PROJECT = "create_new_project"
    REQUEST_APPROVAL = "request_approval"
    ESCALATE = "escalate"


class PriorityFactor(StrEnum):
    """Configurable, explainable inputs to a priority score."""

    MISSION_ALIGNMENT = "mission_alignment"
    STRATEGIC_IMPORTANCE = "strategic_importance"
    DEPENDENCY_IMPACT = "dependency_impact"
    RISK = "risk"
    RESOURCE_COST = "resource_cost"
    DEADLINE_URGENCY = "deadline_urgency"
    BLOCKING = "blocking"


# ── Mission analysis / validation ────────────────────────────────────────────


@dataclass
class MissionAnalysisResult:
    """Structured output of a mission analysis (deterministic or model-backed)."""

    objectives: list[str] = field(default_factory=list)
    target_market: str | None = None
    problem: str | None = None
    proposed_solution: str | None = None
    constraints: list[str] = field(default_factory=list)
    timeline: str | None = None
    success_criteria: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    analyzer: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "objectives": self.objectives,
            "target_market": self.target_market,
            "problem": self.problem,
            "proposed_solution": self.proposed_solution,
            "constraints": self.constraints,
            "timeline": self.timeline,
            "success_criteria": self.success_criteria,
            "assumptions": self.assumptions,
            "risks": self.risks,
            "unknowns": self.unknowns,
            "required_capabilities": self.required_capabilities,
            "analyzer": self.analyzer,
        }


@dataclass
class ValidationIssue:
    """A single validation finding."""

    code: str
    message: str
    severity: str = "error"  # error | warning

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "severity": self.severity}


@dataclass
class ValidationResult:
    """Aggregate validation outcome (errors block, warnings advise)."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def error(self, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(code, message, "error"))

    def warn(self, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(code, message, "warning"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [i.to_dict() for i in self.issues if i.severity == "error"],
            "warnings": [i.to_dict() for i in self.issues if i.severity == "warning"],
        }


# ── Strategic / startup planning ─────────────────────────────────────────────


@dataclass
class StrategyPlanData:
    """Structured strategic plan produced by a StrategicPlanner."""

    vision: str | None = None
    objectives: list[dict[str, Any]] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    milestones: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    resource_estimates: dict[str, Any] = field(default_factory=dict)
    success_metrics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vision": self.vision,
            "objectives": self.objectives,
            "priorities": self.priorities,
            "expected_outcomes": self.expected_outcomes,
            "assumptions": self.assumptions,
            "risks": self.risks,
            "milestones": self.milestones,
            "dependencies": self.dependencies,
            "capabilities": self.capabilities,
            "resource_estimates": self.resource_estimates,
            "success_metrics": self.success_metrics,
        }


@dataclass
class BlueprintDepartment:
    """A department in an organizational blueprint."""

    name: str
    mission: str | None = None
    roles: list[dict[str, Any]] = field(default_factory=list)
    reports_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mission": self.mission,
            "roles": self.roles,
            "reports_to": self.reports_to,
        }


@dataclass
class BlueprintData:
    """A configurable organizational structure (never hardcoded)."""

    departments: list[BlueprintDepartment] = field(default_factory=list)
    authority: dict[str, Any] = field(default_factory=dict)
    kpis: list[dict[str, Any]] = field(default_factory=list)
    budgets: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "departments": [d.to_dict() for d in self.departments],
            "authority": self.authority,
            "kpis": self.kpis,
            "budgets": self.budgets,
        }


@dataclass
class WorkforceDemand:
    """A planned role demand entry."""

    role: str
    department: str | None = None
    count: int = 1
    skills: list[str] = field(default_factory=list)
    priority: int = 0
    workload: dict[str, Any] = field(default_factory=dict)
    monthly_budget: float = 0.0
    authority_level: str = "individual_contributor"
    rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "department": self.department,
            "count": self.count,
            "skills": self.skills,
            "priority": self.priority,
            "workload": self.workload,
            "monthly_budget": self.monthly_budget,
            "authority_level": self.authority_level,
            "rationale": self.rationale,
        }


# ── Operating cycle / observation ────────────────────────────────────────────


@dataclass
class CycleStage:
    """One stage of an operating cycle (immutable timeline entry)."""

    stage: str
    status: str
    summary: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    ended_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "summary": self.summary,
            "metrics": self.metrics,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


@dataclass
class StateSnapshot:
    """Observed company state — every dimension backed by observable metrics."""

    overall_score: float = 0.0
    dimensions: dict[str, float] = field(default_factory=dict)
    explanations: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "dimensions": self.dimensions,
            "explanations": self.explanations,
            "metrics": self.metrics,
        }


@dataclass
class PriorityResult:
    """An explainable priority score for a target."""

    target_type: str
    target_id: UUID
    score: float
    factors: dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "target_id": str(self.target_id),
            "score": self.score,
            "factors": self.factors,
            "reason": self.reason,
        }


# ── Decisions / feedback ─────────────────────────────────────────────────────


@dataclass
class DecisionProposal:
    """A proposed strategic decision — non-executing until reviewed."""

    category: str
    question: str
    options: list[dict[str, Any]] = field(default_factory=list)
    rationale: str | None = None
    risk_level: str = "low"
    evidence: dict[str, Any] = field(default_factory=dict)
    budget_impact: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "question": self.question,
            "options": self.options,
            "rationale": self.rationale,
            "risk_level": self.risk_level,
            "evidence": self.evidence,
            "budget_impact": self.budget_impact,
            "requires_approval": self.requires_approval,
        }


@dataclass
class FeedbackRecord:
    """A structured feedback signal (never auto-executed)."""

    category: str
    observation: str
    source: str | None = None
    impact: str | None = None
    confidence: float = 0.0
    recommendation: str | None = None
    objective_type: dict[str, Any] | None = None
    related_goal_id: UUID | None = None
    related_project_id: UUID | None = None
    related_product_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "observation": self.observation,
            "source": self.source,
            "impact": self.impact,
            "confidence": self.confidence,
            "recommendation": self.recommendation,
            "objective_type": self.objective_type,
            "related_goal_id": str(self.related_goal_id) if self.related_goal_id else None,
            "related_project_id": (
                str(self.related_project_id) if self.related_project_id else None
            ),
            "related_product_id": (
                str(self.related_product_id) if self.related_product_id else None
            ),
        }


# ── Exceptions ───────────────────────────────────────────────────────────────


class StartupEngineError(Exception):
    """Base error for the startup engine (mapped to HTTP 400)."""


class ApprovalRequiredError(StartupEngineError):
    """An action is allowed only after a human approval gate is granted."""

    def __init__(
        self,
        company_id: UUID,
        action: str,
        reason: str,
        gate_type: str | None = None,
    ) -> None:
        self.company_id = company_id
        self.action = action
        self.reason = reason
        self.gate_type = gate_type
        super().__init__(reason)


class AutonomyBlockedError(StartupEngineError):
    """An action is never autonomous for this company; it is refused."""

    def __init__(self, company_id: UUID, action: str, reason: str) -> None:
        self.company_id = company_id
        self.action = action
        self.reason = reason
        super().__init__(reason)


@dataclass
class ReplanDecision:
    """The ReplanningEngine's chosen bounded response to a trigger."""

    trigger: str
    response: ReplanResponse
    reason: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    requires_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "response": self.response.value,
            "reason": self.reason,
            "actions": self.actions,
            "requires_approval": self.requires_approval,
        }
