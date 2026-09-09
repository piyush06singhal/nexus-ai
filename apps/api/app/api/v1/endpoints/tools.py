"""Tool and tool-call endpoints.

GET /tools           — List all registered tool definitions.
GET /tools/{name}    — Get a single tool definition by name.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.session import get_db
from app.schemas.tool import ToolCallRead, ToolRead
from app.services.tool_call_service import ToolCallService, to_dict
from app.tools.registry import get_tool, get_tool_definitions

router = APIRouter(tags=["tools"], prefix="/tools")


@router.get("", response_model=list[ToolRead], summary="List all registered tools")
def list_tools() -> list[ToolRead]:
    """Return definitions for every tool currently registered in the system."""
    defs = get_tool_definitions()
    return [ToolRead.model_validate(d) for d in defs]


@router.get("/{tool_name}", response_model=ToolRead, summary="Get a tool definition")
def get_tool_def(tool_name: str) -> ToolRead:
    """Return the definition of a single tool by name."""
    try:
        tool = get_tool(tool_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ToolRead.model_validate(tool.definition.model_dump())


# --- Tool call records (nested under executions, but exposed here for convenience) ---

@router.get(
    "/calls/{execution_id}",
    response_model=list[ToolCallRead],
    summary="List tool calls for an execution",
)
def list_tool_calls_for_execution(
    execution_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ToolCallRead]:
    """Return all tool call records for a given execution, ordered chronologically."""
    from uuid import UUID

    try:
        eid = UUID(execution_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Invalid execution_id format"
        ) from exc

    service = ToolCallService(db)
    records = service.list_by_execution(eid)
    return [ToolCallRead.model_validate(to_dict(r)) for r in records]
