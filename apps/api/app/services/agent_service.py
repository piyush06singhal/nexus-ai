"""Agent persistence service.

Thin CRUD over the :class:`Agent` ORM model. Keeps DB access out of the
runtime and API layers so they stay testable.
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models.agent import Agent, AgentStatus
from app.schemas.agent import AgentCreate, AgentUpdate


def _serialize_model_params(params: dict | None) -> str | None:
    if params is None:
        return None
    return json.dumps(params)


def _deserialize_model_params(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return None


class AgentService:
    """Create, read, and update agents."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, payload: AgentCreate) -> Agent:
        existing = self._db.scalar(select(Agent).where(Agent.name == payload.name))
        if existing is not None:
            raise ConflictError(f"Agent with name {payload.name!r} already exists")
        agent = Agent(
            name=payload.name,
            role=payload.role,
            description=payload.description,
            status=payload.status,
            system_prompt=payload.system_prompt,
            provider=payload.provider,
            model_name=payload.model_name,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            model_params=_serialize_model_params(payload.model_params),
        )
        self._db.add(agent)
        self._db.commit()
        self._db.refresh(agent)
        return agent

    def get(self, agent_id: UUID) -> Agent:
        agent = self._db.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError(f"Agent {agent_id} not found")
        return agent

    def get_by_name(self, name: str) -> Agent:
        agent = self._db.scalar(select(Agent).where(Agent.name == name))
        if agent is None:
            raise NotFoundError(f"Agent {name!r} not found")
        return agent

    def list(self, *, status: AgentStatus | None = None) -> list[Agent]:
        stmt = select(Agent).order_by(Agent.created_at.desc())
        if status is not None:
            stmt = stmt.where(Agent.status == status)
        return list(self._db.scalars(stmt).all())

    def update(self, agent_id: UUID, payload: AgentUpdate) -> Agent:
        agent = self.get(agent_id)
        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "model_params" in changes:
            changes["model_params"] = _serialize_model_params(changes["model_params"])
        for field, value in changes.items():
            setattr(agent, field, value)
        self._db.commit()
        self._db.refresh(agent)
        return agent

    def delete(self, agent_id: UUID) -> None:
        agent = self.get(agent_id)
        self._db.delete(agent)
        self._db.commit()


def to_dict(agent: Agent) -> dict:
    """Serialize an Agent ORM instance for API responses."""
    return {
        "id": str(agent.id),
        "name": agent.name,
        "role": agent.role,
        "description": agent.description,
        "status": agent.status.value,
        "system_prompt": agent.system_prompt,
        "provider": agent.provider,
        "model_name": agent.model_name,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "model_params": _deserialize_model_params(agent.model_params),
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }
