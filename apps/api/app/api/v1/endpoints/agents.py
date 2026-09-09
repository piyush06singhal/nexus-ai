"""Agent endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.models.agent import AgentStatus
from app.db.session import get_db
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate
from app.services.agent_service import AgentService, to_dict

router = APIRouter(tags=["agents"], prefix="/agents")


@router.get("", response_model=list[AgentRead], summary="List agents")
def list_agents(
    status_filter: AgentStatus | None = Query(default=None, alias="status"),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[AgentRead]:
    service = AgentService(db)
    agents = service.list(status=status_filter)
    return [AgentRead.model_validate(to_dict(a)) for a in agents]


@router.post(
    "", response_model=AgentRead, status_code=status.HTTP_201_CREATED, summary="Create an agent"
)
def create_agent(
    payload: AgentCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> AgentRead:
    service = AgentService(db)
    agent = service.create(payload)
    return AgentRead.model_validate(to_dict(agent))


@router.get("/{agent_id}", response_model=AgentRead, summary="Get an agent")
def get_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> AgentRead:
    service = AgentService(db)
    return AgentRead.model_validate(to_dict(service.get(agent_id)))


@router.patch("/{agent_id}", response_model=AgentRead, summary="Update an agent")
def update_agent(
    agent_id: UUID,
    payload: AgentUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> AgentRead:
    service = AgentService(db)
    agent = service.update(agent_id, payload)
    return AgentRead.model_validate(to_dict(agent))


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an agent")
def delete_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    service = AgentService(db)
    service.delete(agent_id)
