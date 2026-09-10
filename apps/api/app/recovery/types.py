"""Recovery domain types (Phase 6).

Shared dataclasses and exceptions for the recovery engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


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


class RecoveryStrategy(StrEnum):
    """Available recovery strategies (spec §15)."""

    RETRY = "retry"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    RETRY_WITH_MODIFIED_INPUT = "retry_with_modified_input"
    REPLAN = "replan"
    FALLBACK_AGENT = "fallback_agent"
    FALLBACK_TOOL = "fallback_tool"
    SKIP = "skip"
    PARTIAL_COMPLETION = "partial_completion"
    ESCALATE = "escalate"
    ABORT = "abort"


# ── Exceptions ────────────────────────────────────────────────────────────────


class RecoveryError(Exception):
    """Base exception for recovery failures."""


class UnsafeRecoveryError(RecoveryError):
    """Recovery action rejected by safety classifier (§45)."""


class BudgetExhaustedError(RecoveryError):
    """Recovery budget exceeded (§48)."""


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class RecoveryPlan:
    """A recovery plan produced for a failure (spec §20)."""

    request_id: UUID = field(default_factory=uuid4)
    execution_id: UUID | None = None
    orchestration_id: UUID | None = None
    workflow_id: UUID | None = None
    category: str = "unknown"
    severity: str = "medium"
    strategy: RecoveryStrategy = RecoveryStrategy.ABORT
    original_plan: dict | None = None
    revised_plan: dict | None = None
    reason: str | None = None
    affected_tasks: list[str] = field(default_factory=list)
    safety_check: dict | None = None
    budget_remaining: int = 3
    escalate_after: int = 2
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            "request_id": str(self.request_id),
            "execution_id": str(self.execution_id) if self.execution_id else None,
            "orchestration_id": str(self.orchestration_id) if self.orchestration_id else None,
            "workflow_id": str(self.workflow_id) if self.workflow_id else None,
            "category": self.category,
            "severity": self.severity,
            "strategy": self.strategy.value,
            "original_plan": self.original_plan,
            "revised_plan": self.revised_plan,
            "reason": self.reason,
            "affected_tasks": self.affected_tasks,
            "safety_check": self.safety_check,
            "budget_remaining": self.budget_remaining,
            "escalate_after": self.escalate_after,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class RecoveryAttempt:
    """A single recovery attempt and its outcome (spec §17, §39)."""

    id: UUID = field(default_factory=uuid4)
    execution_id: UUID | None = None
    plan_id: UUID | None = None
    attempt_number: int = 1
    state: RecoveryState = RecoveryState.DETECTED
    strategy: RecoveryStrategy | None = None
    verification_result_id: UUID | None = None
    outcome: str | None = None
    reason: str | None = None
    metadata: dict = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "execution_id": str(self.execution_id) if self.execution_id else None,
            "plan_id": str(self.plan_id) if self.plan_id else None,
            "attempt_number": self.attempt_number,
            "state": self.state.value,
            "strategy": self.strategy.value if self.strategy else None,
            "verification_result_id": str(self.verification_result_id)
            if self.verification_result_id
            else None,
            "outcome": self.outcome,
            "reason": self.reason,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class FailureDiagnosis:
    """An evidence-based structured diagnosis of a failure (spec §19)."""

    id: UUID = field(default_factory=uuid4)
    execution_id: UUID | None = None
    category: str = "unknown"
    severity: str = "medium"
    root_cause: str | None = None
    retryable: bool = False
    recommended_strategy: str | None = None
    confidence: float = 0.0
    evidence: dict | list = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "execution_id": str(self.execution_id) if self.execution_id else None,
            "category": self.category,
            "severity": self.severity,
            "root_cause": self.root_cause,
            "retryable": self.retryable,
            "recommended_strategy": self.recommended_strategy,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EscalationContext:
    """Context for an escalation record."""

    execution_id: UUID | None = None
    orchestration_id: UUID | None = None
    workflow_id: UUID | None = None
    issue: str = ""
    category: str = "unknown"
    severity: str = "medium"
    context_data: dict | None = None
