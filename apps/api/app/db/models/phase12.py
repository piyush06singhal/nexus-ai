"""Simulation, Optimization & Agent Marketplace domain models (Phase 12).

The final roadmap phase: NEXUS can simulate organizations, run what-if
experiments, optimize allocation/strategy, benchmark & recommend agents, and
close the loop OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE → EXECUTE →
MEASURE → LEARN → RE-SIMULATE.

Design notes (mirroring project convention):
- References carry identity/lifecycle/state; rich payloads are JSON Text.
- Enum columns use the project's ``_enum_values`` / ``native_enum=False`` /
  ``create_constraint=False`` convention (VARCHAR storage, no native enums).
- Company-scoped tables carry ``company_id`` (UUID FK + index) so nothing ever
  leaks across companies.
- Simulated/optimized/forecast outputs are stored as *modeled estimates* — they
  are never conflated with ACTUAL ``kpi_values`` / ``budgets`` / ``tasks`` rows.
- Marketplace packages are metadata only: capabilities/skills/requirements/
  benchmark results. Credentials/secrets/memories/executable payloads are
  rejected at the API layer, never persisted here.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
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


class SimStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class SimScenarioType(StrEnum):
    BASELINE = "baseline"
    WHAT_IF = "what_if"
    STRESS_TEST = "stress_test"
    CAPACITY_TEST = "capacity_test"
    RESOURCE_TEST = "resource_test"
    STRATEGY_TEST = "strategy_test"
    WORKFORCE_TEST = "workforce_test"
    AGENT_TEST = "agent_test"
    PRODUCT_TEST = "product_test"
    RISK_TEST = "risk_test"
    CUSTOM = "custom"


class SimVariableKind(StrEnum):
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    STRING = "string"
    ENUM = "enum"
    DURATION = "duration"
    PERCENTAGE = "percentage"
    CURRENCY = "currency"
    RATE = "rate"


class SimEventKind(StrEnum):
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    EMPLOYEE_UNAVAILABLE = "employee_unavailable"
    EMPLOYEE_OVERLOADED = "employee_overloaded"
    AGENT_FAILURE = "agent_failure"
    BUDGET_CHANGE = "budget_change"
    PROJECT_DELAY = "project_delay"
    PRODUCT_LAUNCH = "product_launch"
    KPI_THRESHOLD = "kpi_threshold"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    WORKFLOW_FAILURE = "workflow_failure"
    DEPARTMENT_CHANGE = "department_change"
    PRIORITY_CHANGE = "priority_change"
    SANDBOX_REFUSAL = "sandbox_refusal"


class SimulationOutputKind(StrEnum):
    """How a stored simulation output is labeled — never confused with actuals."""

    ACTUAL = "actual"
    SIMULATED = "simulated"
    FORECAST = "forecast"


class SimCheckpointAction(StrEnum):
    CHECKPOINT = "checkpoint"
    RESTORE = "restore"
    RESUME = "resume"


class OptimizationStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OptimizationObjectiveDirection(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class RecommendationStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    EXPIRED = "expired"


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


class ExperimentConclusion(StrEnum):
    WINNER = "winner"
    LOSER = "loser"
    INCONCLUSIVE = "inconclusive"


class BenchmarkStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BenchmarkDimension(StrEnum):
    CORRECTNESS = "correctness"
    RELIABILITY = "reliability"
    TOOL_USAGE = "tool_usage"
    LATENCY = "latency"
    COST = "cost"
    VERIFICATION_SUCCESS = "verification_success"
    RECOVERY = "recovery"
    CONSISTENCY = "consistency"


class PackageStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class CompatLevel(StrEnum):
    COMPATIBLE = "compatible"
    COMPATIBLE_WITH_NOTE = "compatible_with_note"
    INCOMPATIBLE = "incompatible"


class InstallStatus(StrEnum):
    PENDING = "pending"
    APPROVAL_REQUIRED = "approval_required"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    UNINSTALLED = "uninstalled"


class ReputationSource(StrEnum):
    BENCHMARK = "benchmark"
    SUCCESS = "success"
    VERIFICATION_PASS = "verification_pass"
    RECOVERY = "recovery"
    CONSISTENCY = "consistency"
    RATING = "rating"


class SecurityClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class OptimizationCycleStatus(StrEnum):
    OBSERVING = "observing"
    SIMULATING = "simulating"
    OPTIMIZING = "optimizing"
    PROPOSING = "proposing"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    MEASURING = "measuring"
    LEARNING = "learning"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OptimizationLessonKind(StrEnum):
    OPTIMIZATION = "optimization"
    SIMULATION = "simulation"
    EXPERIMENT = "experiment"


# ── Simulation (digital twin, scenarios, runs, comparisons) ──────────────────


class Simulation(Base):
    """A simulation definition: twin, scenario, variables, horizon, status."""

    __tablename__ = "simulations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario_type: Mapped[str] = mapped_column(
        _enum_column(SimScenarioType, "simulation_scenario_type"),
        default=SimScenarioType.CUSTOM.value,
    )
    status: Mapped[str] = mapped_column(
        _enum_column(SimStatus, "simulation_status"), default=SimStatus.DRAFT.value
    )
    # How the model describes itself — reproducibility for reviewers.
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clock_tick: Mapped[str | None] = mapped_column(String(20), nullable=True)  # day|hour|week
    baseline_simulation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    sandboxed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )

    __table_args__ = (
        Index("ix_simulations_company_status", "company_id", "status"),
        Index("ix_simulations_company_scenario", "company_id", "scenario_type"),
    )


class SimulationScenario(Base):
    """A named scenario attached to a simulation (baseline+variables+horizon)."""

    __tablename__ = "simulation_scenarios"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    simulation_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    scenario_type: Mapped[str] = mapped_column(
        _enum_column(SimScenarioType, "scenario_type"), default=SimScenarioType.WHAT_IF.value
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    objective_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # expected metrics
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )

    __table_args__ = (Index("ix_scenarios_sim", "simulation_id"),)


class SimulationVariable(Base):
    """Typed variable driving a scenario (bounds enforced at validation)."""

    __tablename__ = "simulation_variables"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    simulation_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulations.id", ondelete="CASCADE"), index=True
    )
    scenario_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(_enum_column(SimVariableKind, "sim_variable_kind"))
    value: Mapped[str | None] = mapped_column(String(500), nullable=True)  # serialized value
    min_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    max_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    default_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        Index("ix_sim_variables_sim", "simulation_id"),
        Index("ix_sim_variables_scenario", "scenario_id"),
    )


class SimulationAssumption(Base):
    """A stated assumption a simulation run depends on (auditable)."""

    __tablename__ = "simulation_assumptions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    simulation_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())

    __table_args__ = (UniqueConstraint("simulation_id", "key", name="uq_sim_assumption_key"),)


class SimulationRun(Base):
    """One execution of a simulation (inputs, seed, status, outcome summary)."""

    __tablename__ = "simulation_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    simulation_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulations.id", ondelete="CASCADE"), index=True
    )
    scenario_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("simulation_scenarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        _enum_column(SimStatus, "sim_run_status"), default=SimStatus.READY.value
    )
    seed: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tick_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), index=True
    )

    __table_args__ = (
        Index("ix_sim_runs_sim_status", "simulation_id", "status"),
        Index("ix_sim_runs_company", "company_id"),
    )


class SimulationIteration(Base):
    """A single iteration of a multi-run (Monte-Carlo-style) simulation."""

    __tablename__ = "simulation_iterations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    iteration: Mapped[int] = mapped_column(Integer)
    seed: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        _enum_column(SimStatus, "sim_iteration_status"), default=SimStatus.READY.value
    )
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        UniqueConstraint("run_id", "iteration", name="uq_sim_iteration_number"),
        Index("ix_sim_iterations_company", "company_id"),
    )


class SimulationSnapshot(Base):
    """Versioned digital-twin snapshot of a company (read-only, never mutating)."""

    __tablename__ = "simulation_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_company_id: Mapped[UUID] = mapped_column(Uuid, index=True)  # what was captured
    name: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), index=True
    )

    __table_args__ = (Index("ix_snapshot_source", "source_company_id"),)


class SimulationOutcome(Base):
    """Stored simulation result output (labeled SIMULATED/FORECAST)."""

    __tablename__ = "simulation_outcomes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    output_kind: Mapped[str] = mapped_column(
        _enum_column(SimulationOutputKind, "sim_output_kind"),
        default=SimulationOutputKind.SIMULATED.value,
    )
    metric_key: Mapped[str] = mapped_column(String(200), index=True)  # kpi id / domain metric
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scenario_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    outcome_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())

    __table_args__ = (Index("ix_sim_outcomes_run_metric", "run_id", "metric_key"),)


class SimulationMetric(Base):
    __tablename__ = "simulation_metrics"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(200), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class SimulationEvent(Base):
    """An event produced inside a simulation (never drives production)."""

    __tablename__ = "simulation_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    tick: Mapped[int] = mapped_column(Integer, index=True)
    event_kind: Mapped[str] = mapped_column(
        _enum_column(SimEventKind, "sim_event_kind"), index=True
    )
    entity_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())

    __table_args__ = (Index("ix_sim_events_run_tick", "run_id", "tick"),)


class SimulationComparison(Base):
    """Baseline vs scenario comparison (deltas, bottlenecks, pressure)."""

    __tablename__ = "simulation_comparisons"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    baseline_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    scenario_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    metric_deltas_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    bottleneck_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class SimulationCheckpoint(Base):
    """Checkpoint / resume / restore record for long simulations."""

    __tablename__ = "simulation_checkpoints"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(
        _enum_column(SimCheckpointAction, "sim_checkpoint_action"),
        default=SimCheckpointAction.CHECKPOINT.value,
    )
    tick: Mapped[int] = mapped_column(Integer, default=0)
    state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class SimulationEntity(Base):
    """Entity tracked inside a simulation (twin of a company dept/employee/etc)."""

    __tablename__ = "simulation_entities"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(80))  # department|employee|agent|resource
    source_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


# ── Optimization ─────────────────────────────────────────────────────────────


class OptimizationProblem(Base):
    __tablename__ = "optimization_problems"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        _enum_column(OptimizationStatus, "optimization_problem_status"),
        default=OptimizationStatus.DRAFT.value,
    )
    objective_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # weighted objectives
    strategy: Mapped[str | None] = mapped_column(String(80), nullable=True)  # greedy|search|sim...
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )

    __table_args__ = (Index("ix_optim_problems_company", "company_id"),)


class OptimizationVariable(Base):
    __tablename__ = "optimization_variables"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("optimization_problems.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))  # integer|float|category...
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    default: Mapped[float | None] = mapped_column(Float, nullable=True)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class OptimizationConstraint(Base):
    __tablename__ = "optimization_constraints"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("optimization_problems.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. budget <= 1000
    resource_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class OptimizationObjective(Base):
    __tablename__ = "optimization_objectives"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("optimization_problems.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    metric: Mapped[str] = mapped_column(String(200))
    direction: Mapped[str] = mapped_column(
        _enum_column(OptimizationObjectiveDirection, "optim_objective_direction"),
        default=OptimizationObjectiveDirection.MINIMIZE.value,
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("optimization_problems.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        _enum_column(OptimizationStatus, "optimization_run_status"),
        default=OptimizationStatus.READY.value,
    )
    strategy: Mapped[str | None] = mapped_column(String(80), nullable=True)
    constraints_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), index=True
    )

    __table_args__ = (Index("ix_optim_runs_problem", "problem_id"),)


class OptimizationCandidate(Base):
    __tablename__ = "optimization_candidates"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    candidate_index: Mapped[int] = mapped_column(Integer)
    values_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    variables_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    constraints_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    objective_scores_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class OptimizationScore(Base):
    __tablename__ = "optimization_scores"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("optimization_candidates.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    metric: Mapped[str] = mapped_column(String(200))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    normalized: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class OptimizationRecommendation(Base):
    """An explainable, approval-gated recommendation from an optimization run."""

    __tablename__ = "optimization_recommendations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        _enum_column(RecommendationStatus, "opt_recommendation_status"),
        default=RecommendationStatus.PROPOSED.value,
    )
    title: Mapped[str] = mapped_column(String(300))
    candidate_values_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    explanation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # five W's + why
    expected_benefit_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_cost_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approval_gate_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())

    __table_args__ = (Index("ix_opt_recs_company_status", "company_id", "status"),)


class OptimizationLesson(Base):
    """Lesson recorded from an optimization cycle (reuses LessonRecorder)."""

    __tablename__ = "optimization_lessons"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cycle_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(
        _enum_column(OptimizationLessonKind, "optimization_lesson_kind"),
        default=OptimizationLessonKind.OPTIMIZATION.value,
    )
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    source_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    startup_lesson_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


# ── Experiments ──────────────────────────────────────────────────────────────


class Experiment(Base):
    """A controlled experiment (baseline + variants), approval-gated."""

    __tablename__ = "experiments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        _enum_column(ExperimentStatus, "experiment_status"),
        default=ExperimentStatus.DRAFT.value,
    )
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approval_gate_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )

    __table_args__ = (Index("ix_experiments_company_status", "company_id", "status"),)


class ExperimentVariant(Base):
    __tablename__ = "experiment_variants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    variant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("experiment_variants.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        _enum_column(SimStatus, "experiment_run_status"), default=SimStatus.RUNNING.value
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class ExperimentMetric(Base):
    """A metric recorded for an experiment (optionally per variant/run)."""

    __tablename__ = "experiment_metrics"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("experiment_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    variant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(200), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class ExperimentResult(Base):
    __tablename__ = "experiment_results"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    conclusion: Mapped[str] = mapped_column(
        _enum_column(ExperimentConclusion, "experiment_conclusion"),
        default=ExperimentConclusion.INCONCLUSIVE.value,
    )
    winning_variant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    limitations_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recorded_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


# ── Benchmarks & agent scores ───────────────────────────────────────────────


class Benchmark(Base):
    """A benchmark (suite of cases) reused across agents/versions."""

    __tablename__ = "benchmarks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        _enum_column(BenchmarkStatus, "benchmark_status"), default=BenchmarkStatus.DRAFT.value
    )
    version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dimensions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )

    __table_args__ = (Index("ix_benchmarks_company", "company_id"),)


class BenchmarkSuite(Base):
    __tablename__ = "benchmark_suites"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    benchmark_id: Mapped[UUID] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    cases_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class BenchmarkCase(Base):
    __tablename__ = "benchmark_cases"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    suite_id: Mapped[UUID] = mapped_column(
        ForeignKey("benchmark_suites.id", ondelete="CASCADE"), index=True
    )
    benchmark_id: Mapped[UUID] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    benchmark_id: Mapped[UUID] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    agent_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        _enum_column(BenchmarkStatus, "benchmark_run_status"),
        default=BenchmarkStatus.RUNNING.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), index=True
    )

    __table_args__ = (Index("ix_bench_runs_agent", "agent_id"),)


class BenchmarkResult(Base):
    __tablename__ = "benchmark_results"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("benchmark_runs.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("benchmark_cases.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class AgentBenchmarkScore(Base):
    """Versioned aggregate benchmark score for an agent (reputation signal)."""

    __tablename__ = "agent_benchmark_scores"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    benchmark_id: Mapped[UUID] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("benchmark_runs.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    dimension: Mapped[str] = mapped_column(
        _enum_column(BenchmarkDimension, "benchmark_dimension"), index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)
    sample_cases: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), index=True
    )

    __table_args__ = (
        Index("ix_agent_score_agent_dim", "agent_id", "dimension"),
        UniqueConstraint(
            "agent_id", "benchmark_id", "run_id", "dimension", name="uq_agent_benchmark_score"
        ),
    )


# ── Marketplace ─────────────────────────────────────────────────────────────


class AgentPackage(Base):
    """A marketplace agent package — metadata only, never payloads/secrets."""

    __tablename__ = "agent_packages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        _enum_column(PackageStatus, "agent_package_status"), default=PackageStatus.DRAFT.value
    )
    creator_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    capabilities_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    skills_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    supported_task_types_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requirements_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # model/tools/perms
    security: Mapped[str] = mapped_column(
        _enum_column(SecurityClassification, "agent_package_security"),
        default=SecurityClassification.INTERNAL.value,
    )
    documentation_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archival_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )

    __table_args__ = (
        UniqueConstraint("name", "company_id", name="uq_agent_package_name_company"),
        Index("ix_agent_packages_status", "status"),
    )


class AgentPackageVersion(Base):
    """Semver-versioned package release (major.minor.patch)."""

    __tablename__ = "agent_package_versions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    package_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_packages.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    version: Mapped[str] = mapped_column(String(40))  # 1.2.3
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    compatibility: Mapped[str] = mapped_column(
        _enum_column(CompatLevel, "agent_package_compat"),
        default=CompatLevel.COMPATIBLE.value,
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())

    __table_args__ = (UniqueConstraint("package_id", "version", name="uq_agent_package_version"),)


class AgentPackageCapability(Base):
    __tablename__ = "agent_package_capabilities"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_package_versions.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class AgentPackageDependency(Base):
    __tablename__ = "agent_package_dependencies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_package_versions.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    dependency_name: Mapped[str] = mapped_column(String(300))
    dependency_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class AgentPackageBenchmark(Base):
    """Link a package version to its benchmark scores (transparent ranking)."""

    __tablename__ = "agent_package_benchmarks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_package_versions.id", ondelete="CASCADE"), index=True
    )
    benchmark_id: Mapped[UUID] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class AgentPackageReview(Base):
    __tablename__ = "agent_package_reviews"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    package_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_packages.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    reviewer_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    rating: Mapped[int] = mapped_column(Integer, default=0)  # 0-5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class AgentInstallation(Base):
    """A package install into a running company — governed, audited, approved."""

    __tablename__ = "agent_installations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    package_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_packages.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_package_versions.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(
        _enum_column(InstallStatus, "agent_install_status"),
        default=InstallStatus.PENDING.value,
    )
    approval_gate_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    installed_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), index=True
    )

    __table_args__ = (Index("ix_agent_installs_company_status", "company_id", "status"),)


class AgentRecommendation(Base):
    """Ranked agent recommendation with transparent reasons."""

    __tablename__ = "agent_recommendations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    agent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    package_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    tradeoffs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    compatibility: Mapped[str] = mapped_column(
        _enum_column(CompatLevel, "agent_recommend_compat"),
        default=CompatLevel.COMPATIBLE.value,
    )
    policy_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), index=True
    )

    __table_args__ = (Index("ix_agent_recommend_company", "company_id"),)


class AgentReputationRecord(Base):
    """Reputation from measurable signals only — no self-rating/manipulation."""

    __tablename__ = "agent_reputation_records"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(Uuid, nullable=True, index=True)
    company_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    source: Mapped[str] = mapped_column(
        _enum_column(ReputationSource, "reputation_source"), index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), index=True
    )

    __table_args__ = (Index("ix_reputation_agent_source", "agent_id", "source"),)


# ── Closed-loop ──────────────────────────────────────────────────────────────


class AutonomousOptimizationCycle(Base):
    """A whole OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE → EXECUTE →
    MEASURE → LEARN cycle (unified orchestration loop)."""

    __tablename__ = "autonomous_optimization_cycles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        _enum_column(OptimizationCycleStatus, "optimization_cycle_status"),
        default=OptimizationCycleStatus.OBSERVING.value,
    )
    observed_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scenario_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    simulation_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    optimization_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    recommendation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approval_gate_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    execute_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    measures_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lesson_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )

    __table_args__ = (Index("ix_opt_cycles_company_status", "company_id", "status"),)
