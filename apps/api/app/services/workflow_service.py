"""Workflow persistence service.

Thin CRUD and lifecycle management over the workflow ORM models.
Keeps DB access out of the API and engine layers so they stay testable.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.models.workflow import (
    StepExecution,
    Workflow,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowStatus,
    WorkflowStep,
    WorkflowTrigger,
)
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowStepCreate,
    WorkflowStepUpdate,
    WorkflowTriggerCreate,
    WorkflowUpdate,
    WorkflowValidationResult,
)
from app.tools.registry import list_tool_names
from app.workflow.validator import validate_workflow_steps


def _loads(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _dumps(value: dict | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


# ── Serialization helpers ─────────────────────────────────────────────────────


def to_dict(workflow: Workflow) -> dict:
    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "description": workflow.description,
        "status": workflow.status.value,
        "version": workflow.version,
        "configuration": _loads(workflow.configuration),
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
    }


def step_to_dict(step: WorkflowStep) -> dict:
    return {
        "id": str(step.id),
        "workflow_id": str(step.workflow_id),
        "name": step.name,
        "description": step.description,
        "step_type": step.step_type.value,
        "order": step.order,
        "configuration": _loads(step.configuration),
        "dependencies": _loads(step.dependencies),
        "timeout_seconds": step.timeout_seconds,
        "retry_policy": _loads(step.retry_policy),
        "idempotency": step.idempotency.value,
        "created_at": step.created_at,
        "updated_at": step.updated_at,
    }


def trigger_to_dict(trigger: WorkflowTrigger) -> dict:
    return {
        "id": str(trigger.id),
        "workflow_id": str(trigger.workflow_id),
        "trigger_type": trigger.trigger_type.value,
        "configuration": _loads(trigger.configuration),
        "enabled": trigger.enabled,
        "next_run_at": trigger.next_run_at,
        "created_at": trigger.created_at,
        "updated_at": trigger.updated_at,
    }


def execution_to_dict(execution: WorkflowExecution) -> dict:
    return {
        "id": str(execution.id),
        "workflow_id": str(execution.workflow_id),
        "status": execution.status.value,
        "trigger_type": execution.trigger_type,
        "input_data": _loads(execution.input_data),
        "output_data": _loads(execution.output_data),
        "error": execution.error,
        "started_at": execution.started_at,
        "completed_at": execution.completed_at,
        "duration_ms": execution.duration_ms,
        "created_at": execution.created_at,
    }


def step_execution_to_dict(se: StepExecution) -> dict:
    return {
        "id": str(se.id),
        "workflow_execution_id": str(se.workflow_execution_id),
        "workflow_step_id": str(se.workflow_step_id),
        "status": se.status.value,
        "input_data": _loads(se.input_data),
        "output_data": _loads(se.output_data),
        "error": se.error,
        "started_at": se.started_at,
        "completed_at": se.completed_at,
        "duration_ms": se.duration_ms,
        "attempt_number": se.attempt_number,
        "created_at": se.created_at,
    }


# ── Service ───────────────────────────────────────────────────────────────────


class WorkflowService:
    """Create, read, update, and manage workflows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Workflow CRUD ──────────────────────────────────────────────────────

    def create(self, payload: WorkflowCreate) -> Workflow:
        existing = self._db.scalar(select(Workflow).where(Workflow.name == payload.name))
        if existing is not None:
            raise ConflictError(f"Workflow with name {payload.name!r} already exists")
        workflow = Workflow(
            name=payload.name,
            description=payload.description,
            configuration=_dumps(payload.configuration),
        )
        self._db.add(workflow)
        self._db.commit()
        self._db.refresh(workflow)
        return workflow

    def get(self, workflow_id: UUID) -> Workflow:
        workflow = self._db.get(Workflow, workflow_id)
        if workflow is None:
            raise NotFoundError(f"Workflow {workflow_id} not found")
        return workflow

    def list(self, *, status: WorkflowStatus | None = None) -> list[Workflow]:
        stmt = select(Workflow).order_by(Workflow.created_at.desc())
        if status is not None:
            stmt = stmt.where(Workflow.status == status)
        return list(self._db.scalars(stmt).all())

    def update(self, workflow_id: UUID, payload: WorkflowUpdate) -> Workflow:
        workflow = self.get(workflow_id)
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] != workflow.name:
            existing = self._db.scalar(select(Workflow).where(Workflow.name == changes["name"]))
            if existing is not None:
                raise ConflictError(f"Workflow with name {changes['name']!r} already exists")
        if "configuration" in changes:
            changes["configuration"] = _dumps(changes["configuration"])
        for field, value in changes.items():
            setattr(workflow, field, value)
        self._db.commit()
        self._db.refresh(workflow)
        return workflow

    def delete(self, workflow_id: UUID) -> None:
        workflow = self.get(workflow_id)
        if workflow.status == WorkflowStatus.ACTIVE:
            raise ValidationError("Cannot delete an active workflow — pause or archive it first")
        self._db.delete(workflow)
        self._db.commit()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def activate(self, workflow_id: UUID) -> Workflow:
        workflow = self.get(workflow_id)
        # Validate the step graph before activation.
        result = self.validate(workflow_id)
        if not result.valid:
            raise ValidationError(f"Cannot activate workflow: {'; '.join(result.errors)}")
        workflow.status = WorkflowStatus.ACTIVE
        self._db.commit()
        self._db.refresh(workflow)
        return workflow

    def pause(self, workflow_id: UUID) -> Workflow:
        workflow = self.get(workflow_id)
        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValidationError("Can only pause an active workflow")
        workflow.status = WorkflowStatus.PAUSED
        self._db.commit()
        self._db.refresh(workflow)
        return workflow

    # ── Validation ─────────────────────────────────────────────────────────

    def validate(self, workflow_id: UUID) -> WorkflowValidationResult:
        self.get(workflow_id)  # ensure the workflow exists
        steps = self.get_steps(workflow_id)
        # Known tool names come from the live registry; agent references are
        # validated at runtime by the engine (so agents can be added later).
        return validate_workflow_steps(steps, known_tool_names=list_tool_names())

    # ── Steps ──────────────────────────────────────────────────────────────

    def get_steps(self, workflow_id: UUID) -> list[WorkflowStep]:
        stmt = (
            select(WorkflowStep)
            .where(WorkflowStep.workflow_id == workflow_id)
            .order_by(WorkflowStep.order, WorkflowStep.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def get_step(self, step_id: UUID) -> WorkflowStep:
        step = self._db.get(WorkflowStep, step_id)
        if step is None:
            raise NotFoundError(f"WorkflowStep {step_id} not found")
        return step

    def add_step(self, workflow_id: UUID, payload: WorkflowStepCreate) -> WorkflowStep:
        workflow = self.get(workflow_id)
        if workflow.status != WorkflowStatus.DRAFT:
            raise ValidationError("Can only add steps to a draft workflow")
        # Check for duplicate name.
        existing = self._db.scalar(
            select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow_id,
                WorkflowStep.name == payload.name,
            )
        )
        if existing is not None:
            raise ConflictError(f"Step with name {payload.name!r} already exists in this workflow")
        step = WorkflowStep(
            workflow_id=workflow_id,
            name=payload.name,
            description=payload.description,
            step_type=payload.step_type,
            order=payload.order,
            configuration=_dumps(payload.configuration),
            dependencies=json.dumps(payload.dependencies) if payload.dependencies else None,
            timeout_seconds=payload.timeout_seconds,
            retry_policy=_dumps(payload.retry_policy),
            idempotency=payload.idempotency,
        )
        self._db.add(step)
        self._db.commit()
        self._db.refresh(step)
        return step

    def update_step(self, step_id: UUID, payload: WorkflowStepUpdate) -> WorkflowStep:
        step = self.get_step(step_id)
        workflow = self.get(step.workflow_id)
        if workflow.status != WorkflowStatus.DRAFT:
            raise ValidationError("Can only update steps on a draft workflow")
        changes = payload.model_dump(exclude_unset=True)
        if "configuration" in changes:
            changes["configuration"] = _dumps(changes["configuration"])
        if "dependencies" in changes:
            deps = changes["dependencies"]
            changes["dependencies"] = json.dumps(deps) if deps else None
        if "retry_policy" in changes:
            changes["retry_policy"] = _dumps(changes["retry_policy"])
        for field, value in changes.items():
            setattr(step, field, value)
        self._db.commit()
        self._db.refresh(step)
        return step

    def remove_step(self, step_id: UUID) -> None:
        step = self.get_step(step_id)
        workflow = self.get(step.workflow_id)
        if workflow.status != WorkflowStatus.DRAFT:
            raise ValidationError("Can only remove steps from a draft workflow")
        self._db.delete(step)
        self._db.commit()

    # ── Triggers ───────────────────────────────────────────────────────────

    def get_triggers(self, workflow_id: UUID) -> list[WorkflowTrigger]:
        stmt = (
            select(WorkflowTrigger)
            .where(WorkflowTrigger.workflow_id == workflow_id)
            .order_by(WorkflowTrigger.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def add_trigger(self, workflow_id: UUID, payload: WorkflowTriggerCreate) -> WorkflowTrigger:
        self.get(workflow_id)  # Validate workflow exists.
        trigger = WorkflowTrigger(
            workflow_id=workflow_id,
            trigger_type=payload.trigger_type,
            configuration=_dumps(payload.configuration),
            enabled=payload.enabled,
        )
        self._db.add(trigger)
        self._db.commit()
        self._db.refresh(trigger)
        return trigger

    def remove_trigger(self, trigger_id: UUID) -> None:
        trigger = self._db.get(WorkflowTrigger, trigger_id)
        if trigger is None:
            raise NotFoundError(f"WorkflowTrigger {trigger_id} not found")
        self._db.delete(trigger)
        self._db.commit()

    # ── Executions ─────────────────────────────────────────────────────────

    def create_execution(
        self,
        workflow_id: UUID,
        *,
        trigger_type: str | None = None,
        input_data: dict | None = None,
    ) -> WorkflowExecution:
        workflow = self.get(workflow_id)
        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValidationError("Can only execute active workflows")
        execution = WorkflowExecution(
            id=uuid4(),
            workflow_id=workflow_id,
            status=WorkflowExecutionStatus.QUEUED,
            trigger_type=trigger_type,
            input_data=_dumps(input_data),
        )
        self._db.add(execution)
        self._db.commit()
        self._db.refresh(execution)
        return execution

    def get_execution(self, execution_id: UUID) -> WorkflowExecution:
        execution = self._db.get(WorkflowExecution, execution_id)
        if execution is None:
            raise NotFoundError(f"WorkflowExecution {execution_id} not found")
        return execution

    def list_executions(self, workflow_id: UUID) -> list[WorkflowExecution]:
        stmt = (
            select(WorkflowExecution)
            .where(WorkflowExecution.workflow_id == workflow_id)
            .order_by(WorkflowExecution.created_at.desc())
        )
        return list(self._db.scalars(stmt).all())

    def cancel_execution(self, execution_id: UUID) -> WorkflowExecution:
        execution = self.get_execution(execution_id)
        if execution.status not in (
            WorkflowExecutionStatus.QUEUED,
            WorkflowExecutionStatus.RUNNING,
        ):
            raise ValidationError(f"Cannot cancel execution in {execution.status.value!r} status")
        execution.status = WorkflowExecutionStatus.CANCELLED
        execution.completed_at = datetime.now(UTC)
        self._db.commit()
        self._db.refresh(execution)
        return execution

    def get_step_executions(self, execution_id: UUID) -> list[StepExecution]:
        stmt = (
            select(StepExecution)
            .where(StepExecution.workflow_execution_id == execution_id)
            .order_by(StepExecution.created_at)
        )
        return list(self._db.scalars(stmt).all())
