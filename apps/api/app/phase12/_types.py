"""Phase 12 shared types and status enums (mirror model enum values)."""

from __future__ import annotations

from enum import StrEnum


class SimRunStatus(StrEnum):
    """Lifecycle of a simulation or run."""

    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class SimScenario(StrEnum):
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


class OptimizationStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


class BenchmarkStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


class RecommendationStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    EXPIRED = "expired"


# Guard that service enums mirror the model enums exactly (drift protection).
def _assert_enum_alignment() -> None:  # pragma: no cover - exercised at import
    from app.db.models import phase12 as model_models

    pairs = (
        (SimRunStatus, model_models.SimStatus),
        (SimScenario, model_models.SimScenarioType),
        (SimVariableKind, model_models.SimVariableKind),
        (OptimizationStatus, model_models.OptimizationStatus),
        (ExperimentStatus, model_models.ExperimentStatus),
        (BenchmarkStatus, model_models.BenchmarkStatus),
        (OptimizationCycleStatus, model_models.OptimizationCycleStatus),
        (RecommendationStatus, model_models.RecommendationStatus),
    )
    for service_enum, model_enum in pairs:
        if [m.value for m in service_enum] != [m.value for m in model_enum]:
            raise RuntimeError(
                f"Phase 12 enum drift: {service_enum.__name__} != {model_enum.__name__}"
            )


_assert_enum_alignment()
