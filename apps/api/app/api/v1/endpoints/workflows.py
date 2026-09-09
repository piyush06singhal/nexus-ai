"""Workflow orchestration endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.db.session import get_db
from app.schemas.workflow import (
    StepExecutionRead,
    WorkflowCreate,
    WorkflowExecuteRequest,
    WorkflowExecutionRead,
    WorkflowRead,
    WorkflowStepCreate,
    WorkflowStepRead,
    WorkflowStepUpdate,
    WorkflowTriggerCreate,
    WorkflowTriggerRead,
    WorkflowUpdate,
    WorkflowValidationResult,
)
from app.services.workflow_service import (
    WorkflowService,
    execution_to_dict,
    step_execution_to_dict,
    step_to_dict,
    to_dict,
    trigger_to_dict,
)

router = APIRouter(tags=["workflows"], prefix="/workflows")


# ── Workflow CRUD ─────────────────────────────────────────────────────────────


@router.get("", response_model=list[WorkflowRead], summary="List workflows")
def list_workflows(
    status_filter: str | None = Query(default=None, alias="status"),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[WorkflowRead]:
    svc = WorkflowService(db)
    from app.db.models.workflow import WorkflowStatus

    wf_status = None
    if status_filter:
        try:
            wf_status = WorkflowStatus(status_filter)
        except ValueError:
            raise ValidationError(f"Invalid status: {status_filter!r}") from None
    workflows = svc.list(status=wf_status)
    return [WorkflowRead.model_validate(to_dict(w)) for w in workflows]


@router.post(
    "",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workflow",
)
def create_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowRead:
    svc = WorkflowService(db)
    return WorkflowRead.model_validate(to_dict(svc.create(payload)))


@router.get("/{workflow_id}", response_model=WorkflowRead, summary="Get a workflow")
def get_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowRead:
    svc = WorkflowService(db)
    return WorkflowRead.model_validate(to_dict(svc.get(workflow_id)))


@router.patch("/{workflow_id}", response_model=WorkflowRead, summary="Update a workflow")
def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowRead:
    svc = WorkflowService(db)
    return WorkflowRead.model_validate(to_dict(svc.update(workflow_id, payload)))


@router.delete(
    "/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a workflow"
)
def delete_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    svc = WorkflowService(db)
    svc.delete(workflow_id)


# ── Lifecycle ─────────────────────────────────────────────────────────────────


@router.post("/{workflow_id}/activate", response_model=WorkflowRead, summary="Activate a workflow")
def activate_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowRead:
    svc = WorkflowService(db)
    return WorkflowRead.model_validate(to_dict(svc.activate(workflow_id)))


@router.post("/{workflow_id}/pause", response_model=WorkflowRead, summary="Pause a workflow")
def pause_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowRead:
    svc = WorkflowService(db)
    return WorkflowRead.model_validate(to_dict(svc.pause(workflow_id)))


# ── Validation ────────────────────────────────────────────────────────────────


@router.get(
    "/{workflow_id}/validate",
    response_model=WorkflowValidationResult,
    summary="Validate a workflow's step graph",
)
def validate_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowValidationResult:
    svc = WorkflowService(db)
    return svc.validate(workflow_id)


# ── Steps ─────────────────────────────────────────────────────────────────────


@router.get(
    "/{workflow_id}/steps",
    response_model=list[WorkflowStepRead],
    summary="List steps for a workflow",
)
def list_steps(
    workflow_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[WorkflowStepRead]:
    svc = WorkflowService(db)
    steps = svc.get_steps(workflow_id)
    return [WorkflowStepRead.model_validate(step_to_dict(s)) for s in steps]


@router.post(
    "/{workflow_id}/steps",
    response_model=WorkflowStepRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a step to a workflow",
)
def create_step(
    workflow_id: UUID,
    payload: WorkflowStepCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowStepRead:
    svc = WorkflowService(db)
    return WorkflowStepRead.model_validate(step_to_dict(svc.add_step(workflow_id, payload)))


@router.patch("/steps/{step_id}", response_model=WorkflowStepRead, summary="Update a step")
def update_step(
    step_id: UUID,
    payload: WorkflowStepUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowStepRead:
    svc = WorkflowService(db)
    return WorkflowStepRead.model_validate(step_to_dict(svc.update_step(step_id, payload)))


@router.delete("/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a step")
def delete_step(
    step_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    svc = WorkflowService(db)
    svc.remove_step(step_id)


# ── Triggers ──────────────────────────────────────────────────────────────────


@router.get(
    "/{workflow_id}/triggers",
    response_model=list[WorkflowTriggerRead],
    summary="List triggers for a workflow",
)
def list_triggers(
    workflow_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[WorkflowTriggerRead]:
    svc = WorkflowService(db)
    triggers = svc.get_triggers(workflow_id)
    return [WorkflowTriggerRead.model_validate(trigger_to_dict(t)) for t in triggers]


@router.post(
    "/{workflow_id}/triggers",
    response_model=WorkflowTriggerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a trigger to a workflow",
)
def create_trigger(
    workflow_id: UUID,
    payload: WorkflowTriggerCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowTriggerRead:
    svc = WorkflowService(db)
    return WorkflowTriggerRead.model_validate(
        trigger_to_dict(svc.add_trigger(workflow_id, payload))
    )


@router.delete(
    "/triggers/{trigger_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a trigger",
)
def delete_trigger(
    trigger_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    svc = WorkflowService(db)
    svc.remove_trigger(trigger_id)


# ── Execute ───────────────────────────────────────────────────────────────────


@router.post(
    "/{workflow_id}/execute",
    response_model=WorkflowExecutionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Execute a workflow",
)
def execute_workflow(
    workflow_id: UUID,
    payload: WorkflowExecuteRequest | None = None,  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowExecutionRead:
    svc = WorkflowService(db)
    input_data = payload.input_data if payload else None
    execution = svc.create_execution(
        workflow_id,
        trigger_type="manual",
        input_data=input_data,
    )

    if settings.workflow_execute_sync:
        # Run inline for tests — deterministic, no worker needed.
        from app.workflow.engine import WorkflowEngine

        engine = WorkflowEngine(db)
        execution = engine.execute(execution.id)
    return WorkflowExecutionRead.model_validate(execution_to_dict(execution))


# ── Executions ────────────────────────────────────────────────────────────────


@router.get(
    "/{workflow_id}/executions",
    response_model=list[WorkflowExecutionRead],
    summary="List executions for a workflow",
)
def list_executions(
    workflow_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[WorkflowExecutionRead]:
    svc = WorkflowService(db)
    executions = svc.list_executions(workflow_id)
    return [WorkflowExecutionRead.model_validate(execution_to_dict(e)) for e in executions]


@router.get(
    "/executions/{execution_id}",
    response_model=WorkflowExecutionRead,
    summary="Get an execution",
)
def get_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowExecutionRead:
    svc = WorkflowService(db)
    return WorkflowExecutionRead.model_validate(execution_to_dict(svc.get_execution(execution_id)))


@router.get(
    "/executions/{execution_id}/steps",
    response_model=list[StepExecutionRead],
    summary="List step executions for an execution",
)
def list_step_executions(
    execution_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[StepExecutionRead]:
    svc = WorkflowService(db)
    ses = svc.get_step_executions(execution_id)
    return [StepExecutionRead.model_validate(step_execution_to_dict(s)) for s in ses]


@router.post(
    "/executions/{execution_id}/cancel",
    response_model=WorkflowExecutionRead,
    summary="Cancel a running execution",
)
def cancel_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkflowExecutionRead:
    svc = WorkflowService(db)
    return WorkflowExecutionRead.model_validate(
        execution_to_dict(svc.cancel_execution(execution_id))
    )
