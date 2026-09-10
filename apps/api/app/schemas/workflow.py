"""Pydantic API schemas for workflows.

Mirror the ORM models in :mod:`app.db.models.workflow` but stay decoupled
from SQLAlchemy so they can validate API input and serialize API output.

``configuration`` is free-form (``dict[str, Any]``) for each entity — the
engine interprets it based on the step type / trigger type.  The DB stores
it as a JSON string; the ``to_dict`` helpers handle the round-trip.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.workflow import (
    IdempotencyTag,
    StepStatus,
    TriggerType,
    WorkflowExecutionStatus,
    WorkflowStatus,
    WorkflowStepType,
)

# ── Workflow ─────────────────────────────────────────────────────────────────


class WorkflowCreate(BaseModel):
    """Payload to create a new workflow."""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    configuration: dict[str, Any] | None = None


class WorkflowUpdate(BaseModel):
    """Partial update payload for a workflow.  All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    configuration: dict[str, Any] | None = None


class WorkflowRead(BaseModel):
    """Full workflow representation returned by the API."""

    id: UUID
    name: str
    description: str | None = None
    status: WorkflowStatus
    version: int
    configuration: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── WorkflowStep ─────────────────────────────────────────────────────────────


class WorkflowStepCreate(BaseModel):
    """Payload to add a step to a workflow."""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    step_type: WorkflowStepType
    order: int = 0
    configuration: dict[str, Any] | None = None
    dependencies: list[str] | None = None
    timeout_seconds: int | None = Field(default=None, gt=0)
    retry_policy: dict[str, Any] | None = None
    idempotency: IdempotencyTag = IdempotencyTag.NON_IDEMPOTENT
    verification_policy: dict[str, Any] | None = None


class WorkflowStepUpdate(BaseModel):
    """Partial update payload for a step."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    step_type: WorkflowStepType | None = None
    order: int | None = None
    configuration: dict[str, Any] | None = None
    dependencies: list[str] | None = None
    timeout_seconds: int | None = Field(default=None, gt=0)
    retry_policy: dict[str, Any] | None = None
    idempotency: IdempotencyTag | None = None
    verification_policy: dict[str, Any] | None = None


class WorkflowStepRead(BaseModel):
    """Full step representation returned by the API."""

    id: UUID
    workflow_id: UUID
    name: str
    description: str | None = None
    step_type: WorkflowStepType
    order: int
    configuration: dict[str, Any] | None = None
    dependencies: list[str] | None = None
    timeout_seconds: int | None = None
    retry_policy: dict[str, Any] | None = None
    idempotency: IdempotencyTag
    verification_policy: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── WorkflowTrigger ──────────────────────────────────────────────────────────


class WorkflowTriggerCreate(BaseModel):
    """Payload to add a trigger to a workflow."""

    trigger_type: TriggerType
    configuration: dict[str, Any] | None = None
    enabled: bool = True


class WorkflowTriggerRead(BaseModel):
    """Full trigger representation returned by the API."""

    id: UUID
    workflow_id: UUID
    trigger_type: TriggerType
    configuration: dict[str, Any] | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── WorkflowExecution ────────────────────────────────────────────────────────


class WorkflowExecutionRead(BaseModel):
    """Full execution representation returned by the API."""

    id: UUID
    workflow_id: UUID
    status: WorkflowExecutionStatus
    trigger_type: str | None = None
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── StepExecution ────────────────────────────────────────────────────────────


class StepExecutionRead(BaseModel):
    """Full step-execution representation returned by the API."""

    id: UUID
    workflow_execution_id: UUID
    workflow_step_id: UUID
    status: StepStatus
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    attempt_number: int
    verification_run_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Validation & Execute ─────────────────────────────────────────────────────


class WorkflowValidationResult(BaseModel):
    """Outcome of validating a workflow's step graph."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkflowExecuteRequest(BaseModel):
    """Optional body for the execute endpoint."""

    input_data: dict[str, Any] | None = None
