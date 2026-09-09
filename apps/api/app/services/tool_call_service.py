"""Tool call persistence service.

Creates and queries :class:`ToolCallRecord` ORM rows. The executor calls
this to persist the outcome of each tool invocation.
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models.tool_call import ToolCallRecord


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return None


class ToolCallService:
    """Create and query tool call records."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_execution(self, execution_id: UUID) -> list[ToolCallRecord]:
        """Return all tool calls for a given execution, ordered by creation."""
        stmt = (
            select(ToolCallRecord)
            .where(ToolCallRecord.execution_id == execution_id)
            .order_by(ToolCallRecord.created_at.asc())
        )
        return list(self._db.scalars(stmt).all())

    def get(self, tool_call_id: UUID) -> ToolCallRecord:
        """Return a single tool call by ID."""
        tc = self._db.get(ToolCallRecord, tool_call_id)
        if tc is None:
            raise NotFoundError(f"Tool call {tool_call_id} not found")
        return tc

    def count_by_execution(self, execution_id: UUID) -> int:
        """Return the number of tool calls for an execution."""
        stmt = (
            select(ToolCallRecord)
            .where(ToolCallRecord.execution_id == execution_id)
        )
        return len(list(self._db.scalars(stmt).all()))


def to_dict(tc: ToolCallRecord) -> dict:
    """Serialize a ToolCallRecord ORM instance for API responses."""
    return {
        "id": str(tc.id),
        "execution_id": str(tc.execution_id),
        "tool_name": tc.tool_name,
        "arguments": _loads(tc.arguments),
        "result_status": tc.result_status.value,
        "result_data": _loads(tc.result_data),
        "result_error": tc.result_error,
        "execution_time_ms": tc.execution_time_ms,
        "iteration": tc.iteration,
        "created_at": tc.created_at,
    }
