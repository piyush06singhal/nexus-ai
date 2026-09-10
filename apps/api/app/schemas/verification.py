"""Pydantic API schemas for verification (Phase 6).

Mirror the verification ORM models but stay decoupled from SQLAlchemy so they
can validate API input and serialize API output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.reliability import VerificationStatus


class VerificationPolicyCreate(BaseModel):
    """Payload to create a verification policy."""

    name: str = Field(min_length=1, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)
    scope_type: str | None = Field(default=None, max_length=32)
    scope_id: UUID | None = None


class VerificationPolicyRead(BaseModel):
    """Verification policy representation returned by the API."""

    id: UUID
    name: str
    config: dict[str, Any] | None = None
    scope_type: str | None = None
    scope_id: UUID | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationRunRead(BaseModel):
    """Verification run representation returned by the API."""

    id: UUID
    execution_id: UUID | None = None
    task_id: UUID | None = None
    orchestration_id: UUID | None = None
    workflow_id: UUID | None = None
    policy_id: UUID | None = None
    strategy_used: str | None = None
    status: VerificationStatus
    score: float | None = None
    confidence: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationResultRead(BaseModel):
    """Verification result representation returned by the API."""

    id: UUID
    run_id: UUID
    execution_id: UUID | None = None
    verifier_type: str | None = None
    verifier_id: UUID | None = None
    status: VerificationStatus
    score: float
    confidence: float
    reason: str | None = None
    failed_criteria: list[str] | None = None
    passed_criteria: list[str] | None = None
    evidence: list[Any] | None = None
    recommendations: list[str] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerifyRequest(BaseModel):
    """Payload to trigger verification of an execution's result."""

    execution_id: UUID | None = None
    result_data: dict[str, Any] | None = None
    risk_level: str = Field(default="medium", pattern="^(low|medium|high)$")
    policy_override: dict[str, Any] | None = None


class VerificationListResponse(BaseModel):
    """Paginated (simple) list of verification runs."""

    runs: list[VerificationRunRead]
    total: int
