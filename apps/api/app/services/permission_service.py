"""Tool permission persistence service.

Loads and saves per-agent tool permissions from the ``agent_tool_permissions``
table. The executor uses this to build a :class:`PermissionContext` before
running any tool.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.agent_tool_permission import AgentToolPermission
from app.tools.permissions import PermissionContext


class PermissionService:
    """Load and manage per-agent tool permissions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_context(self, agent_id: UUID) -> PermissionContext:
        """Build a :class:`PermissionContext` from the DB for the given agent."""
        stmt = select(AgentToolPermission).where(AgentToolPermission.agent_id == agent_id)
        rows = list(self._db.scalars(stmt).all())

        allowed: set[str] = set()
        denied: set[str] = set()

        for row in rows:
            if row.granted:
                allowed.add(row.tool_name)
            else:
                denied.add(row.tool_name)

        return PermissionContext(
            agent_id=agent_id,
            allowed_tools=allowed,
            denied_tools=denied,
        )

    def set_permission(self, agent_id: UUID, tool_name: str, granted: bool) -> AgentToolPermission:
        """Create or update a permission for a specific agent and tool."""
        # Check for existing permission.
        stmt = select(AgentToolPermission).where(
            AgentToolPermission.agent_id == agent_id,
            AgentToolPermission.tool_name == tool_name,
        )
        existing = self._db.scalar(stmt)

        if existing is not None:
            existing.granted = granted
            self._db.commit()
            self._db.refresh(existing)
            return existing

        perm = AgentToolPermission(
            agent_id=agent_id,
            tool_name=tool_name,
            granted=granted,
        )
        self._db.add(perm)
        self._db.commit()
        self._db.refresh(perm)
        return perm

    def revoke(self, agent_id: UUID, tool_name: str) -> None:
        """Remove a specific permission record."""
        stmt = select(AgentToolPermission).where(
            AgentToolPermission.agent_id == agent_id,
            AgentToolPermission.tool_name == tool_name,
        )
        perm = self._db.scalar(stmt)
        if perm is not None:
            self._db.delete(perm)
            self._db.commit()

    def list_for_agent(self, agent_id: UUID) -> list[AgentToolPermission]:
        """Return all permission records for a given agent."""
        stmt = (
            select(AgentToolPermission)
            .where(AgentToolPermission.agent_id == agent_id)
            .order_by(AgentToolPermission.tool_name)
        )
        return list(self._db.scalars(stmt).all())
