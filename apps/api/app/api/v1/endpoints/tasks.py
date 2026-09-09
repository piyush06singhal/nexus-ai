"""Task endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.execution import AgentExecution
from app.db.models.task import TaskStatus
from app.db.session import get_db
from app.runtime import AgentRuntime
from app.schemas.execution import ExecutionRead
from app.schemas.task import TaskCreate, TaskRead
from app.services.dependencies import create_runtime
from app.services.execution_service import ExecutionService
from app.services.execution_service import to_dict as execution_to_dict
from app.services.task_service import TaskService, to_dict


class AssignRequest(BaseModel):
    """Request body for assigning a task to an agent."""

    agent_id: UUID


router = APIRouter(tags=["tasks"], prefix="/tasks")


@router.get("", response_model=list[TaskRead], summary="List tasks")
def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[TaskRead]:
    service = TaskService(db)
    tasks = service.list(status=status_filter)
    return [TaskRead.model_validate(to_dict(t)) for t in tasks]


@router.post(
    "", response_model=TaskRead, status_code=status.HTTP_201_CREATED, summary="Create a task"
)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> TaskRead:
    service = TaskService(db)
    task = service.create(payload)
    return TaskRead.model_validate(to_dict(task))


@router.get("/{task_id}", response_model=TaskRead, summary="Get a task")
def get_task(
    task_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> TaskRead:
    service = TaskService(db)
    return TaskRead.model_validate(to_dict(service.get(task_id)))


@router.post("/{task_id}/assign", response_model=TaskRead, summary="Assign a task to an agent")
def assign_task(
    task_id: UUID,
    payload: AssignRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> TaskRead:
    service = TaskService(db)
    task = service.assign(task_id, payload.agent_id)
    return TaskRead.model_validate(to_dict(task))


@router.get(
    "/{task_id}/executions", response_model=list[ExecutionRead], summary="List a task's executions"
)
def list_task_executions(
    task_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ExecutionRead]:
    service = ExecutionService(db)
    executions = service.list_by_task(task_id)
    return [ExecutionRead.model_validate(execution_to_dict(e)) for e in executions]


@router.post(
    "/{task_id}/execute",
    response_model=ExecutionRead,
    summary="Execute a task with its assigned agent",
)
def execute_task(
    task_id: UUID,
    runtime: AgentRuntime = Depends(create_runtime),  # noqa: B008
) -> ExecutionRead:
    execution: AgentExecution = runtime.execute_task(task_id)
    return ExecutionRead.model_validate(execution_to_dict(execution))
