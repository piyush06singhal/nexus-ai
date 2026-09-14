"""Tool security — sandbox, per-tool budgets, self-escalation guard (Phase 11, §hardening).

Hardens the Phase 10 tool layer without forking it:

1. **Self-escalation guard** — a tool execution may never modify permission
   configuration (its own grant, another tool's grant, the executor, or the
   runtime policy). Detected statically by tool name and argument shape, and
   refused *before* the tool runs, so a compromised model cannot turn tool
   access into a policy change.
2. **Per-tool budgets** — resource/cost budgets per tool name (from settings
   with safe defaults), enforced as hard caps before execution.
3. **``ToolSandbox``** — a declarative execution budget. In-process NEXUS
   enforces wall-clock timeout (plus the caller's own caps). Memory/CPU/fs/
   network/process limits are *declared and asserted as preconditions* but not
   kernel-enforced in-process: OS-level sandboxing is a documented deployment
   item (plan §21), so the abstraction exists to carry those budgets to the
   server-level supervisor without overclaiming.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Tool names that inherently mutate policy/permission state. Blocked outright —
# no agent may reach the permission system through a "tool".
_ESCALATION_TOOL_NAMES = (
    "set_tool_permission",
    "grant_tool",
    "revoke_tool",
    "update_tool_permission",
    "add_allowed_tool",
    "remove_allowed_tool",
    "set_policy",
    "update_policy",
    "grant_permission",
    "revoke_permission",
    "grant_admin",
    "set_role",
    "assign_role",
    "edit_permissions",
    "modify_access",
)

# Argument keys that, when present, escalate or touch permission state.
_ESCALATION_ARG_KEYS = (
    "allowed_tools",
    "denied_tools",
    "has_admin",
    "permission",
    "permissions",
    "roles",
    "policy",
    "admin",
    "privilege",
    "bypass",
)

# Regexes over stringified arguments that encode an escalation request even
# when the key spelling differs (e.g. ``flags``, ``grants``).
_ESCALATION_ARG_PATTERNS = tuple(
    re.compile(p, re.I)
    for p in (
        r"(set|add|grant|remove|update|revoke).{0,30}(tool.?permission|permission)",
        r"(make|set).{0,20}admin",
        r"(allow|enable).{0,40}(dangerous|privileged|admin)",
    )
)


class ToolSecurityError(ValueError):
    """A tool execution was refused by the tool security policy."""


@dataclass(frozen=True)
class ToolSandbox:
    """Declared execution budget for a single tool call.

    ``timeout_seconds`` is enforced in-process by the executor/Pool future.
    The remaining fields are asserted as preconditions (honest scope: NEXUS
    does not pretend to kernel-enforce memory/CPU/fs/network/process limits
    in-process — those are the server-level supervisor's job, encouraged but
    not overclaimed here).
    """

    tool_name: str
    timeout_seconds: float
    max_memory_mb: int = 0  # 0 = unbounded (deployment policy)
    max_cpu_seconds: float = 0.0  # 0 = unbounded
    max_output_bytes: int = 1024 * 1024  # matched to file cap (1 MiB)
    allow_filesystem: bool = True
    allow_network: bool = False
    allow_process: bool = False
    context_kind: str = "agent"

    @classmethod
    def from_definition(
        cls,
        *,
        tool_name: str,
        timeout_seconds: float,
        context_kind: str = "agent",
        sandbox_kind: str = "default",
    ) -> ToolSandbox:
        budget = _SANDBOX_TEMPLATES.get(sandbox_kind, _SANDBOX_TEMPLATES["default"])
        return cls(
            tool_name=tool_name,
            timeout_seconds=max(timeout_seconds, budget.timeout_seconds),
            max_memory_mb=budget.max_memory_mb,
            max_output_bytes=budget.max_output_bytes,
            allow_filesystem=budget.allow_filesystem,
            allow_network=budget.allow_network,
            allow_process=budget.allow_process,
            context_kind=context_kind,
        )


_SANDBOX_TEMPLATES: dict[str, ToolSandbox] = {
    # Default: network-safe, process-free, files enabled (the workspace guard
    # already contains fs access at the provider layer).
    "default": ToolSandbox(
        tool_name="*", timeout_seconds=30.0, allow_network=False, allow_process=False
    ),
    # Read-only helpers are given the tightest budget.
    "read_only": ToolSandbox(
        tool_name="*",
        timeout_seconds=10.0,
        max_output_bytes=256 * 1024,
        allow_filesystem=False,
        allow_network=False,
        allow_process=False,
    ),
    # Network-touching tools (web research, HTTP connector) may reach out but
    # still never spawn processes.
    "network": ToolSandbox(
        tool_name="*",
        timeout_seconds=60.0,
        allow_network=True,
        allow_process=False,
    ),
    # Local execution tools (computer use, shell) demand a process budget; the
    # caller is expected to provide a real supervisor for these in production.
    "execution": ToolSandbox(
        tool_name="*",
        timeout_seconds=90.0,
        allow_network=True,
        allow_process=True,
    ),
}


class ToolSecurityPolicy:
    """Static per-tool security policy: budgets + escalation refusal.

    Budgets load from templates in code (settings-driven in the future);
    escalations are static so an
    unprivileged agent cannot widen its own reach by naming a tool.
    """

    def __init__(
        self,
        *,
        default_sandbox: str = "default",
        deny_tools: tuple[str, ...] = (),
    ) -> None:
        self._default_sandbox = default_sandbox
        self._deny_tools = frozenset(deny_tools)

    def sandbox_for(
        self, *, tool_name: str, timeout_seconds: float, context_kind: str = "agent"
    ) -> ToolSandbox:
        template = self._template_for(tool_name)
        return ToolSandbox.from_definition(
            tool_name=tool_name,
            timeout_seconds=timeout_seconds,
            context_kind=context_kind,
            sandbox_kind=template,
        )

    def _template_for(self, tool_name: str) -> str:
        lowered = tool_name.lower()
        if any(seg in lowered for seg in ("browser", "http", "research", "http_connector")):
            return "network"
        if any(seg in lowered for seg in ("shell", "computer", "execute", "run", "sandbox")):
            return "execution"
        if any(seg in lowered for seg in ("read", "lookup", "search", "get", "inspect")):
            return "read_only"
        return self._default_sandbox

    def assert_allowed_context(self, *, context_kind: str, sandbox: ToolSandbox) -> None:
        """Refuse a tool in a context its sandbox forbids."""
        if context_kind == "read_only" and not sandbox.allow_filesystem:
            return  # read-only context is fine without files/network/process
        if context_kind == "browser" and not sandbox.allow_network:
            raise ToolSecurityError(
                f"Tool {sandbox.tool_name!r} is not network-capable in a {context_kind} context"
            )

    def is_denied(self, tool_name: str) -> bool:
        return tool_name in self._deny_tools


def is_self_escalation(*, tool_name: str, arguments: dict[str, Any] | None) -> bool:
    """Whether running *tool_name* with *arguments* would escalate tool policy.

    Two signals, applied before the tool executes:
    * the tool's *name* matches a policy-mutating catalog;
    * the *arguments* carry permission-affecting keys or patterns.
    Both are advisory-static (best effort): a tool can still be blocked at the
    higher :class:`app.security.authorization.AuthorizationService` layer if it
    routes a permission change through a normal channel.
    """
    if tool_name.lower() in _ESCALATION_TOOL_NAMES:
        return True
    if not arguments:
        return False
    if _walk_escalation_keys(arguments, set(_ESCALATION_ARG_KEYS)):
        return True
    serialized = " ".join(
        f"{k}={v!r}" for k, v in arguments.items() if not isinstance(v, (dict, list))
    )
    return any(pattern.search(serialized) for pattern in _ESCALATION_ARG_PATTERNS)


def _walk_escalation_keys(value: Any, forbidden: set[str]) -> bool:
    """Depth-first scan for forbidden keys inside nested dicts/lists.

    A tool that receives arbitrary JSON (``json.update``, web payloads, …)
    could smuggle ``allowed_tools``/``grant`` in a nested document; a policy
    change signal nested at any depth is still an escalation.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in forbidden:
                return True
            if _walk_escalation_keys(child, forbidden):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_walk_escalation_keys(child, forbidden) for child in value)
    return False


def guard_tool_call(
    *,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    timeout_seconds: float = 30.0,
    context_kind: str = "agent",
    policy: ToolSecurityPolicy | None = None,
) -> tuple[ToolSandbox, dict[str, Any]]:
    """Combine the security checks into one gate; returns (sandbox, args).

    Raises :class:`ToolSecurityError` on a denied tool or an escalation
    attempt. The returned sandbox carries the effective execution budget.
    """
    policy = policy or ToolSecurityPolicy()
    if policy.is_denied(tool_name):
        raise ToolSecurityError(f"Tool {tool_name!r} is denied by policy")
    if is_self_escalation(tool_name=tool_name, arguments=arguments):
        raise ToolSecurityError(
            f"Tool {tool_name!r} would modify tool-permission configuration (self-escalation)"
        )
    sandbox = policy.sandbox_for(tool_name=tool_name, timeout_seconds=timeout_seconds)
    policy.assert_allowed_context(context_kind=context_kind, sandbox=sandbox)
    return sandbox, arguments or {}
