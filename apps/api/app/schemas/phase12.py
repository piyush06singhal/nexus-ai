"""Phase 12 domain schemas (Simulation, Optimization & Agent Marketplace).

Public/input schemas for the Phase 12 surface, reusing ``_StrictModel`` from
``app.schemas.security`` (``from_attributes`` + ``str_strip_whitespace``) so
ORM → schema validation works. Simulated/optimized outputs are labeled
``output_kind`` (simulated|forecast) — never serialized as ACTUAL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.security import _StrictModel

# ── Simulation ───────────────────────────────────────────────────────────────


class SimulationVariableInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = "float"
    value: str | None = None
    min_value: str | None = None
    max_value: str | None = None
    default_value: str | None = None
    description: str | None = None
    source: str | None = None
    confidence: float | None = None


class SimulationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    company_id: UUID | None = None
    scenario_type: str = "custom"
    assumptions: dict[str, Any] | None = None
    horizon_days: int | None = Field(default=None, ge=1, le=3650)
    clock_tick: str | None = None  # day | hour | week
    variables: list[SimulationVariableInput] = Field(default_factory=list)
    baseline_simulation_id: UUID | None = None


class SimulationPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    name: str
    description: str | None = None
    scenario_type: str
    status: str
    model_name: str | None = None
    model_version: str | None = None
    assumptions_json: dict[str, Any] | None = None
    horizon_days: int | None = None
    clock_tick: str | None = None
    baseline_simulation_id: UUID | None = None
    sandboxed: bool
    created_at: datetime
    updated_at: datetime


class SimulationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    assumptions: dict[str, Any] | None = None
    horizon_days: int | None = None
    clock_tick: str | None = None


class SimulationRunCreate(BaseModel):
    scenario_id: UUID | None = None
    seed: str | None = None
    iterations: int | None = Field(default=None, ge=1, le=200)


class SimulationRunPublic(_StrictModel):
    id: UUID
    simulation_id: UUID
    scenario_id: UUID | None = None
    company_id: UUID | None = None
    status: str
    seed: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    tick_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    summary_json: dict[str, Any] | None = None
    created_at: datetime


class ScenarioCreate(BaseModel):
    simulation_id: UUID
    name: str = Field(min_length=1, max_length=200)
    scenario_type: str = "what_if"
    description: str | None = None
    company_id: UUID | None = None
    assumptions: dict[str, Any] | None = None
    horizon_days: int | None = None
    objective: dict[str, Any] | None = None
    is_baseline: bool = False
    variables: list[SimulationVariableInput] = Field(default_factory=list)


class ScenarioPublic(_StrictModel):
    id: UUID
    simulation_id: UUID
    company_id: UUID | None = None
    name: str
    scenario_type: str
    description: str | None = None
    assumptions_json: dict[str, Any] | None = None
    horizon_days: int | None = None
    is_baseline: bool
    created_at: datetime


class SimulationComparisonPublic(_StrictModel):
    id: UUID
    baseline_run_id: UUID
    scenario_run_id: UUID | None = None
    company_id: UUID | None = None
    metric_deltas_json: dict[str, Any] | None = None
    bottleneck_json: dict[str, Any] | None = None
    summary: str | None = None
    created_at: datetime


class SimulationSnapshotPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    source_company_id: UUID
    name: str
    model_version: str | None = None
    snapshot_json: dict[str, Any] | None = None
    created_at: datetime


class SimulationStatePublic(_StrictModel):
    """A run's live state: clock tick, entity snapshots, recent events."""

    run_id: UUID
    status: str
    tick: int
    simulation_id: UUID
    scenario_id: UUID | None = None
    entities: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)


class SimulationEventPublic(_StrictModel):
    id: UUID
    run_id: UUID
    tick: int
    event_kind: str
    entity_ref: str | None = None
    detail_json: dict[str, Any] | None = None


class SimulationMetricsPublic(BaseModel):
    run_id: UUID
    metrics: list[dict[str, Any]] = Field(default_factory=list)


class SimulationResultsPublic(BaseModel):
    """Multi-run aggregate (modeled estimates — never predictions)."""

    run_id: UUID
    iterations: int
    summary_json: dict[str, Any] | None = None
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    outcomes: list[dict[str, Any]] = Field(default_factory=list)


# ── Optimization ─────────────────────────────────────────────────────────────


class OptimizationObjectiveInput(BaseModel):
    metric: str
    direction: str = "maximize"
    weight: float = 1.0


class OptimizationVariableInput(BaseModel):
    name: str
    kind: str = "float"
    low: float | None = None
    high: float | None = None
    default: float | None = None
    options: list[Any] | None = None


class OptimizationProblemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    company_id: UUID | None = None
    strategy: str | None = None
    objectives: list[OptimizationObjectiveInput] = Field(default_factory=list)
    variables: list[OptimizationVariableInput] = Field(default_factory=list)
    constraints: list[dict[str, Any]] | None = None


class OptimizationProblemPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    name: str
    description: str | None = None
    status: str
    objective_json: dict[str, Any] | None = None
    strategy: str | None = None
    created_at: datetime
    updated_at: datetime


class OptimizationRunPublic(_StrictModel):
    id: UUID
    problem_id: UUID
    company_id: UUID | None = None
    status: str
    strategy: str | None = None
    constraints_json: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result_json: dict[str, Any] | None = None
    created_at: datetime


class OptimizationResultsPublic(BaseModel):
    run_id: UUID
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    best_candidate: dict[str, Any] | None = None


class RecommendationPublic(_StrictModel):
    id: UUID
    run_id: UUID
    company_id: UUID | None = None
    status: str
    title: str
    candidate_values_json: dict[str, Any] | None = None
    explanation_json: dict[str, Any] | None = None
    expected_benefit_json: dict[str, Any] | None = None
    expected_cost_json: dict[str, Any] | None = None
    risk_json: dict[str, Any] | None = None
    assumptions_json: dict[str, Any] | None = None
    approval_gate_id: UUID | None = None
    approved_at: datetime | None = None
    rejected_reason: str | None = None
    applied_ref: str | None = None
    created_at: datetime


class RecommendationReject(BaseModel):
    reason: str | None = None


# ── Experiments ───────────────────────────────────────────────────────────────


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    company_id: UUID | None = None
    hypothesis: str | None = None
    sample_size: int | None = None
    metrics: list[str] | None = None
    baseline: dict[str, Any] | None = None
    variants: list[dict[str, Any]] = Field(default_factory=list)


class ExperimentPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    name: str
    description: str | None = None
    status: str
    hypothesis: str | None = None
    sample_size: int | None = None
    metrics_json: dict[str, Any] | None = None
    baseline_json: dict[str, Any] | None = None
    approval_gate_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ExperimentResultPublic(_StrictModel):
    id: UUID
    experiment_id: UUID
    conclusion: str
    winning_variant_id: UUID | None = None
    sample_size: int | None = None
    metrics_json: dict[str, Any] | None = None
    confidence_json: dict[str, Any] | None = None
    assumptions_json: dict[str, Any] | None = None
    limitations_json: dict[str, Any] | None = None
    created_at: datetime


# ── Benchmarks ────────────────────────────────────────────────────────────────


class BenchmarkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    company_id: UUID | None = None
    version: str | None = None
    dimensions: list[str] | None = None
    cases: list[dict[str, Any]] | None = None


class BenchmarkPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    name: str
    description: str | None = None
    status: str
    version: str | None = None
    dimensions_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class BenchmarkRunPublic(_StrictModel):
    id: UUID
    benchmark_id: UUID
    agent_id: UUID | None = None
    agent_version: str | None = None
    company_id: UUID | None = None
    status: str
    case_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class BenchmarkResultsPublic(BaseModel):
    run_id: UUID
    benchmark_id: UUID
    results: list[dict[str, Any]] = Field(default_factory=list)
    aggregate: dict[str, Any] | None = None


class AgentBenchmarkScorePublic(_StrictModel):
    id: UUID
    agent_id: UUID | None = None
    benchmark_id: UUID
    dimension: str
    score: float
    sample_cases: int = 0
    created_at: datetime


# ── Marketplace ───────────────────────────────────────────────────────────────


class PackageVersionInput(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    changelog: str | None = None
    compatibility: str = "compatible"
    metadata: dict[str, Any] | None = None
    capabilities: list[str] = Field(default_factory=list)
    dependencies: list[dict[str, str]] = Field(default_factory=list)


class AgentPackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    display_name: str | None = None
    description: str | None = None
    company_id: UUID | None = None
    capabilities: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    supported_task_types: list[str] = Field(default_factory=list)
    requirements: dict[str, Any] | None = None
    security: str = "internal"
    version: PackageVersionInput | None = None


class AgentPackagePublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    name: str
    display_name: str | None = None
    description: str | None = None
    status: str
    capabilities_json: dict[str, Any] | None = None
    skills_json: dict[str, Any] | None = None
    supported_task_types_json: dict[str, Any] | None = None
    requirements_json: dict[str, Any] | None = None
    security: str
    published_at: datetime | None = None
    deprecated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentPackageVersionPublic(_StrictModel):
    id: UUID
    package_id: UUID
    version: str
    changelog: str | None = None
    compatibility: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime


class InstallRequest(BaseModel):
    package_id: UUID
    company_id: UUID
    version_id: UUID | None = None
    config: dict[str, Any] | None = None
    require_approval: bool = True


class InstallationPublic(_StrictModel):
    id: UUID
    package_id: UUID
    version_id: UUID | None = None
    company_id: UUID
    employee_id: UUID | None = None
    agent_id: UUID | None = None
    status: str
    approval_gate_id: UUID | None = None
    config_json: dict[str, Any] | None = None
    installed_at: datetime | None = None
    created_at: datetime


class AgentRecommendationPublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    task_id: UUID | None = None
    agent_id: UUID | None = None
    package_id: UUID | None = None
    request_json: dict[str, Any] | None = None
    rank: int
    score: float
    reasoning: str | None = None
    tradeoffs_json: dict[str, Any] | None = None
    compatibility: str
    policy_status: str | None = None
    created_at: datetime


class ReputationPublic(_StrictModel):
    id: UUID
    agent_id: UUID | None = None
    company_id: UUID | None = None
    source: str
    score: float
    sample_size: int = 0
    recorded_at: datetime


# ── Closed-loop ───────────────────────────────────────────────────────────────


class OptimizationCyclePublic(_StrictModel):
    id: UUID
    company_id: UUID | None = None
    name: str
    status: str
    observed_json: dict[str, Any] | None = None
    scenario_ids_json: list[Any] | None = None
    simulation_run_id: UUID | None = None
    optimization_run_id: UUID | None = None
    recommendation_id: UUID | None = None
    approval_gate_id: UUID | None = None
    execute_ref: str | None = None
    measures_json: dict[str, Any] | None = None
    lesson_json: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    updated_at: datetime


class OptimizationCycleCreate(BaseModel):
    company_id: UUID
    name: str = Field(min_length=1, max_length=200)
    observe: bool = True
