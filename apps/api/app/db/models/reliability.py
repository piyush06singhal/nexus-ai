"""Reliability domain models (Phase 6).

Verification, Recovery & Evaluation. These tables record the reliability
lifecycle that sits on top of the execution pipeline from Phases 1–5: whether a
produced result was *correct* (verification), how a failure was classified,
planned and recovered (recovery), when a human must be involved (escalation),
and how well the system performed overall (evaluation).

Design notes (mirroring the project convention):
- Structured fields (criteria lists, evidence, plans, metrics) are stored as
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
    Boolean,
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


# ── Verification enums ────────────────────────────────────────────────────────


class VerificationStatus(StrEnum):
    """Outcome status of a verification run / result."""

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"


# ── Recovery / escalation enums ───────────────────────────────────────────────


class FailureCategory(StrEnum):
    """Structured failure taxonomy (spec §14)."""

    VALIDATION_FAILURE = "validation_failure"
    MODEL_FAILURE = "model_failure"
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    PERMISSION_FAILURE = "permission_failure"
    INVALID_INPUT = "invalid_input"
    INVALID_OUTPUT = "invalid_output"
    DEPENDENCY_FAILURE = "dependency_failure"
    MEMORY_FAILURE = "memory_failure"
    COMMUNICATION_FAILURE = "communication_failure"
    RESOURCE_LIMIT = "resource_limit"
    VERIFICATION_FAILURE = "verification_failure"
    SYSTEM_FAILURE = "system_failure"
    UNKNOWN = "unknown"


class FailureSeverity(StrEnum):
    """Severity of a failure (spec §14)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryState(StrEnum):
    """Recovery state machine (spec §17)."""

    DETECTED = "detected"
    CLASSIFIED = "classified"
    RECOVERY_PLANNED = "recovery_planned"
    RECOVERING = "recovering"
    RETRYING = "retrying"
    REPLANNING = "replanning"
    FALLBACK = "fallback"
    REVERIFIED = "reverified"
    RECOVERED = "recovered"
    FAILED = "failed"
    ESCALATED = "escalated"
    ABORTED = "aborted"
    PARTIALLY_RECOVERED = "partially_recovered"


class EscalationState(StrEnum):
    """Lifecycle of a human-in-the-loop escalation (spec §25)."""

    PENDING_HUMAN_REVIEW = "pending_human_review"
    APPROVED = "approved"
    REJECTED = "rejected"


# ── Tables ────────────────────────────────────────────────────────────────────


class VerificationPolicy(Base):
    """A persisted, configurable verification policy scoped to an entity.

    The JSON ``config`` holds the same fields as the ``VerificationPolicy``
    dataclass: ``required``, ``strategies``, ``minimum_score``,
    ``minimum_confidence``, ``max_attempts``, ``allowed_verifier_types``,
    ``escalation_behavior``, ``retry_behavior``.
    """

    __tablename__ = "verification_policies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    json_config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_verification_policies_scope", "scope_type", "scope_id"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VerificationPolicy id={self.id} name={self.name!r} scope={self.scope_type}>"


class VerificationRun(Base):
    """A single execution of a verification policy against an execution."""

    __tablename__ = "verification_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    execution_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    task_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    orchestration_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    workflow_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    policy_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    strategy_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[VerificationStatus] = mapped_column(
        _enum_column(VerificationStatus, "verification_status"),
        nullable=False,
        default=VerificationStatus.SKIPPED,
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_verification_runs_status", "status"),
        Index("ix_verification_runs_created", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VerificationRun id={self.id} status={self.status.value}>"


class VerificationResult(Base):
    """A structured, machine-readable verification outcome (spec §3)."""

    __tablename__ = "verification_results"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("verification_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    verifier_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verifier_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[VerificationStatus] = mapped_column(
        _enum_column(VerificationStatus, "verification_result_status"),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    passed_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict/list
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_verification_results_status", "status"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VerificationResult id={self.id} status={self.status.value}>"


class FailureDiagnosis(Base):
    """An evidence-based structured diagnosis of a failure (spec §19)."""

    __tablename__ = "failure_diagnoses"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    execution_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    category: Mapped[FailureCategory] = mapped_column(
        _enum_column(FailureCategory, "failure_category"),
        nullable=False,
        default=FailureCategory.UNKNOWN,
    )
    severity: Mapped[FailureSeverity] = mapped_column(
        _enum_column(FailureSeverity, "failure_severity"),
        nullable=False,
        default=FailureSeverity.MEDIUM,
    )
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recommended_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict/list

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<FailureDiagnosis id={self.id} category={self.category.value}>"


class RecoveryPlan(Base):
    """A recovery plan produced for a failure (spec §20)."""

    __tablename__ = "recovery_plans"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    execution_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    orchestration_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    workflow_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    category: Mapped[FailureCategory] = mapped_column(
        _enum_column(FailureCategory, "recovery_plan_category"),
        nullable=False,
        default=FailureCategory.UNKNOWN,
    )
    severity: Mapped[FailureSeverity] = mapped_column(
        _enum_column(FailureSeverity, "recovery_plan_severity"),
        nullable=False,
        default=FailureSeverity.MEDIUM,
    )
    strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    original_plan: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    revised_plan: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_tasks: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    safety_check: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict
    planner_info: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RecoveryPlan id={self.id} strategy={self.strategy}>"


class RecoveryAttempt(Base):
    """A single recovery attempt and its outcome (spec §17, §39)."""

    __tablename__ = "recovery_attempts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    execution_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    plan_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("recovery_plans.id", ondelete="CASCADE"), nullable=True, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[RecoveryState] = mapped_column(
        _enum_column(RecoveryState, "recovery_state"),
        nullable=False,
        default=RecoveryState.DETECTED,
    )
    strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verification_result_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_recovery_attempts_execution_created", "execution_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RecoveryAttempt id={self.id} state={self.state.value}>"


class Escalation(Base):
    """A persistent pending-human-review record for escalated issues (§24, §25).

    An escalation is never auto-approved by the producing agent; a human must
    approve/reject it via the API.
    """

    __tablename__ = "escalations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    execution_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    orchestration_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    workflow_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[FailureCategory] = mapped_column(
        _enum_column(FailureCategory, "escalation_category"),
        nullable=False,
        default=FailureCategory.UNKNOWN,
    )
    severity: Mapped[FailureSeverity] = mapped_column(
        _enum_column(FailureSeverity, "escalation_severity"),
        nullable=False,
        default=FailureSeverity.MEDIUM,
    )
    state: Mapped[EscalationState] = mapped_column(
        _enum_column(EscalationState, "escalation_state"),
        nullable=False,
        default=EscalationState.PENDING_HUMAN_REVIEW,
    )
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_escalations_state", "state"),
        Index("ix_escalations_created", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Escalation id={self.id} state={self.state.value}>"


# ── Evaluation tables ─────────────────────────────────────────────────────────


class Evaluation(Base):
    """A named evaluation (a suite definition) targeting some entity type."""

    __tablename__ = "evaluations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Evaluation id={self.id} name={self.name!r}>"


class EvaluationRun(Base):
    """A single execution of an evaluation suite (§35)."""

    __tablename__ = "evaluation_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    evaluation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_evaluation_runs_created", "created_at"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EvaluationRun id={self.id} status={self.status}>"


class EvaluationCase(Base):
    """An individual evaluated case within an evaluation (§34)."""

    __tablename__ = "evaluation_cases"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    evaluation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    input: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    expected_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    criteria: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EvaluationCase id={self.id} name={self.name!r}>"


class EvaluationResult(Base):
    """The outcome of one case within one run (§30)."""

    __tablename__ = "evaluation_results"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("evaluation_cases.id", ondelete="CASCADE"), nullable=True
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EvaluationResult id={self.id} passed={self.passed}>"


class EvaluationMetric(Base):
    """One named metric value associated with a run (§31)."""

    __tablename__ = "evaluation_metrics"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EvaluationMetric run={self.run_id} metric={self.metric_key}={self.value}>"
