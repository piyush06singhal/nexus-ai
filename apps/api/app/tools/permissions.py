"""Tool permission checking.

Determines whether a given agent is allowed to execute a particular tool.
Permission rules are enforced *before* the executor runs the tool.

The permission model is simple in Phase 2:
    1. Non-dangerous tools are always allowed.
    2. Dangerous tools require explicit permission via the
       ``agent_tool_permissions`` table (or the registry-wide default).
    3. A per-agent allowlist can restrict which tools an agent may use
       regardless of whether they are dangerous.

This module is intentionally decoupled from the DB — the caller (executor)
passes in the permission context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.tools.types import ToolDefinition


@dataclass(frozen=True)
class PermissionContext:
    """Permission state for a single agent executing tools.

    Attributes:
        agent_id: The agent requesting tool execution.
        allowed_tools: Explicit allowlist of tool names (empty = all tools).
        denied_tools: Explicit denylist of tool names.
        has_admin: If True, bypass all permission checks.
    """

    agent_id: UUID
    allowed_tools: set[str] = field(default_factory=set)
    denied_tools: set[str] = field(default_factory=set)
    has_admin: bool = False


def check_permission(tool_def: ToolDefinition, context: PermissionContext) -> bool:
    """Return True if the agent in *context* may execute *tool_def*.

    Rules (evaluated in order):
        1. Admin bypass → always allowed.
        2. Explicit deny → always denied.
        3. If the agent has an allowlist and the tool is not in it → denied.
        4. Dangerous tool without explicit permission → denied.
        5. Everything else → allowed.
    """
    if context.has_admin:
        return True

    if tool_def.name in context.denied_tools:
        return False

    if context.allowed_tools and tool_def.name not in context.allowed_tools:
        return False

    if tool_def.dangerous and tool_def.name not in context.allowed_tools:
        return False

    return True
