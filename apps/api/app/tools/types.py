"""Shared type definitions for the tool system.

These payload types are tool-agnostic: they describe what a tool *can* do,
what it *did* do, and what it *received* as input — regardless of which
specific tool is behind it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ToolParameterType(StrEnum):
    """Primitive parameter types a tool can accept."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ToolParameter(BaseModel):
    """Describes a single parameter a tool accepts.

    Attributes:
        name: Parameter identifier.
        type: Primitive type.
        description: Human-readable explanation.
        required: Whether the parameter must be supplied.
        default: Default value if not provided.
        enum: Allowed values (for string parameters).
    """

    name: str
    type: ToolParameterType
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None


class ToolDefinition(BaseModel):
    """Complete description of a tool — what it does, what it accepts, and
    what it returns.

    Tools are *declared* via definitions and *registered* with the tool
    registry. An agent receives tool definitions so it can decide which
    tool to call and how to populate the arguments.

    Attributes:
        name: Unique tool identifier (lowercase, underscored).
        description: One-line human-readable purpose.
        parameters: Accepted parameters.
        dangerous: If True, requires explicit permission before execution.
        timeout_seconds: Maximum wall-clock seconds before the tool is killed.
        tags: Grouping tags (e.g. ``["math", "utility"]``).
    """

    name: str
    description: str
    parameters: list[ToolParameter] = Field(default_factory=list)
    dangerous: bool = False
    timeout_seconds: float = 30.0
    tags: list[str] = Field(default_factory=list)


class ToolResultStatus(StrEnum):
    """Outcome of a single tool execution."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    DENIED = "denied"


class ToolResult(BaseModel):
    """The outcome of executing a tool.

    Returned to the runtime so the agent can observe the result and
    continue reasoning.

    Attributes:
        status: Outcome indicator.
        data: Structured output payload (tool-specific).
        error: Error message when status is not SUCCESS.
        execution_time_ms: Wall-clock duration of the execution.
    """

    status: ToolResultStatus
    data: Any = None
    error: str | None = None
    execution_time_ms: float | None = None


class ToolCallRecord(BaseModel):
    """Transient record of a single tool invocation within an execution.

    This is *not* the DB model — it's the payload the executor returns
    so the runtime can persist it and the agent can observe it.

    Attributes:
        id: Unique call identifier.
        tool_name: Which tool was called.
        arguments: Arguments supplied by the agent.
        result: Execution outcome.
        iteration: Which iteration of the tool loop this call occurred in.
    """

    id: UUID = Field(default_factory=uuid4)
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: ToolResult
    iteration: int = 1
