"""FastAPI dependencies that assemble the agent runtime.

Exposes a ``create_runtime`` dependency the API layer depends on. Tests can
override this dependency (or the provider it resolves) to inject a mock
without touching production wiring.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.runtime.runtime import AgentRuntime
from app.services.agent_service import AgentService
from app.services.execution_service import ExecutionService
from app.services.task_service import TaskService


def create_runtime(db: Session = Depends(get_db)) -> AgentRuntime:  # noqa: B008
    """Build an AgentRuntime wired to the request-scoped DB session.

    The provider is resolved lazily per execution from the agent's
    ``provider`` field, so no concrete provider is instantiated here.
    """
    return AgentRuntime(
        agent_service=AgentService(db),
        task_service=TaskService(db),
        execution_service=ExecutionService(db),
    )
