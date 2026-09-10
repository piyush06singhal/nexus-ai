"""Agent capability vocabulary and resolution.

Agents expose metadata (role, description, granted tools) the selection layer
matches against a task's ``required_capabilities``. Capabilities are derived
deterministically from an agent's ``role`` and its granted tool permissions —
no schema change to the Phase 1 ``agents`` table, but the seed of a richer
capability model for later phases.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.agent import Agent, AgentStatus
from app.services.permission_service import PermissionService

# Canonical capability keys used by planners and selectors.
RESEARCH = "research"
ANALYSIS = "analysis"
FACT_CHECKING = "fact_checking"
WRITING = "writing"
SUMMARIZATION = "summarization"
DATA_PROCESSING = "data_processing"
GENERAL = "general"

CANONICAL_CAPABILITIES: frozenset[str] = frozenset(
    {RESEARCH, ANALYSIS, FACT_CHECKING, WRITING, SUMMARIZATION, DATA_PROCESSING, GENERAL}
)

# Role → capabilities mapping. Roles are free-form; unknown roles fall back to
# GENERAL so an orchestration can always find *some* agent.
_ROLE_CAPABILITIES: dict[str, list[str]] = {
    "researcher": [RESEARCH, SUMMARIZATION],
    "research": [RESEARCH, SUMMARIZATION],
    "analyst": [ANALYSIS, DATA_PROCESSING, SUMMARIZATION],
    "analysis": [ANALYSIS, DATA_PROCESSING, SUMMARIZATION],
    "fact_checker": [FACT_CHECKING, ANALYSIS],
    "fact-checker": [FACT_CHECKING, ANALYSIS],
    "writer": [WRITING, SUMMARIZATION],
    "writing": [WRITING, SUMMARIZATION],
    "summarizer": [SUMMARIZATION, GENERAL],
}

# Tool name → capability: an agent that holds a tool permission can also claim
# the capability it implies, so tool access surfaces in selection.
_TOOL_CAPABILITIES: dict[str, str] = {
    "calculator": DATA_PROCESSING,
    "datetime": DATA_PROCESSING,
    "text_utils": WRITING,
    "json_utils": DATA_PROCESSING,
}


def capabilities_for_role(role: str | None) -> list[str]:
    """Return the canonical capabilities implied by an agent's *role*."""
    if not role:
        return [GENERAL]
    normalized = role.strip().lower().replace("_", "-").replace(" ", "-")
    caps = list(_ROLE_CAPABILITIES.get(normalized, []))
    if not caps:
        caps = [GENERAL]
    return caps


def capabilities_for_tool(tool_name: str) -> str | None:
    """Return a canonical capability implied by having a tool permission."""
    return _TOOL_CAPABILITIES.get(tool_name)


def resolve_agent_capabilities(agent: Agent, db: Session) -> list[str]:
    """Return the union of role- and tool-derived capabilities for *agent*.

    The set is de-duplicated and sorted for determinism, which keeps agent
    selection and serialization stable across calls.
    """
    caps = set(capabilities_for_role(agent.role))
    perms = PermissionService(db).list_for_agent(agent.id)
    for perm in perms:
        if perm.granted:
            tool_cap = capabilities_for_tool(perm.tool_name)
            if tool_cap:
                caps.add(tool_cap)
    return sorted(caps)


def agent_is_available(agent: Agent) -> bool:
    """Whether an agent is eligible for selection in an orchestration."""
    return agent.status == AgentStatus.ACTIVE and bool(agent.provider and agent.model_name)
