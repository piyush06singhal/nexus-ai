"""Pydantic API schemas for recovery (Phase 6).

Mirror the recovery ORM models but stay decoupled from SQLAlchemy so they
can validate API input and serialize API output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models.reliability import EscalationState, FailureCategory, RecoveryState


class RecoverRequest(BaseModel):
    """Payload to trigger recovery for a failed execution."""

    execution_id: UUID
    error_text: str | None = None
    exception_type: str | None = None
    tool_call_status: str | None = None
    tool_call_result: dict[str, Any] | None = None
    original_plan: dict[str, Any] | None = None


class RecoveryDiagnosisRead(BaseModel):
    """Failure diagnosis representation returned by the API."""

    id: UUID
    execution_id: UUID | None = None
    category: FailureCategory
    severity: str
    root_cause: str | None = None
    retryable: bool
    recommended_strategy: str | None = None
    confidence: float
    evidence: dict[str, Any] | list[Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecoveryPlanRead(BaseModel):
    """Recovery plan representation returned by the API."""

    id: UUID
    execution_id: UUID | None = None
    orchestration_id: UUID | None = None
    workflow_id: UUID | None = None
    category: FailureCategory
    severity: str
    strategy: str | None = None
    original_plan: dict[str, Any] | None = None
    revised_plan: dict[str, Any] | None = None
    reason: str | None = None
    affected_tasks: list[str] | None = None
    safety_check: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecoveryAttemptRead(BaseModel):
    """Recovery attempt representation returned by the API."""

    id: UUID
    execution_id: UUID | None = None
    plan_id: UUID | None = None
    attempt_number: int
    state: RecoveryState
    strategy: str | None = None
    verification_result_id: UUID | None = None
    outcome: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EscalationRead(BaseModel):
    """Escalation representation returned by the API."""

    id: UUID
    execution_id: UUID | None = None
    orchestration_id: UUID | None = None
    workflow_id: UUID | None = None
    issue: str
    category: FailureCategory
    severity: str
    state: EscalationState
    context: dict[str, Any] | None = None
    decision_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EscalationDecision(BaseModel):
    """Payload for approving/rejecting an escalation."""

    decision_reason: str | None = None


class EscalationListResponse(BaseModel):
    """Paginated (simple) list of escalations."""

    escalations: list[EscalationRead]
    total: int
