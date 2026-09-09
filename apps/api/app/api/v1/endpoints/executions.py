"""Execution endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.models.execution import AgentExecution
from app.db.session import get_db
from app.schemas.execution import ExecutionRead
from app.services.execution_service import ExecutionService, to_dict

router = APIRouter(tags=["executions"], prefix="/executions")


@router.get("", response_model=list[ExecutionRead], summary="List recent executions (activity)")
def list_executions(
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ExecutionRead]:
    service = ExecutionService(db)
    executions = service.list_all(limit=limit)
    return [ExecutionRead.model_validate(to_dict(e)) for e in executions]


@router.get("/{execution_id}", response_model=ExecutionRead, summary="Get an execution")
def get_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> ExecutionRead:
    service = ExecutionService(db)
    execution: AgentExecution = service.get(execution_id)
    return ExecutionRead.model_validate(to_dict(execution))
