"""Context builder.

Builds the ``ChatMessage`` conversation for an agent task execution from the
agent's configuration, the task description, the task input payload, and —
when tool calling is enabled — the available tool definitions and prior
tool call results.
"""

from __future__ import annotations

import json

from app.ai.types import ChatMessage
from app.db.models.agent import AgentStatus
from app.db.models.task import Task
from app.tools.types import ToolCallRecord, ToolResultStatus


def build_context(
    agent,
    task: Task,
    *,
    tool_definitions: list[dict] | None = None,
) -> list[ChatMessage]:
    """Construct the messages sent to the model for ``task`` executed by ``agent``.

    The conversation shape is:
        [system (agent.system_prompt + role + tools), user (task details + input)]

    When *tool_definitions* are supplied, the system prompt includes tool
    usage instructions and the user message concludes with a structured
    output contract that supports tool calls.
    """
    system_lines: list[str] = []
    if agent.role:
        system_lines.append(f"You are the {agent.role} agent named {agent.name!r}.")
    if agent.system_prompt:
        system_lines.append(agent.system_prompt)
    if not system_lines:
        system_lines.append(
            f"You are an autonomous agent named {agent.name!r}. Complete the assigned task."
        )

    # Append tool definitions to the system prompt when available.
    if tool_definitions:
        tools_block = _format_tool_definitions(tool_definitions)
        system_lines.append(tools_block)

    system_prompt = "\n\n".join(system_lines)

    user_lines = [f"# Task: {task.title}"]
    if task.description:
        user_lines.append(task.description)
    if task.input_data:
        try:
            payload = json.loads(task.input_data)
            user_lines.append("\n# Input:\n```json\n" + json.dumps(payload, indent=2) + "\n```")
        except json.JSONDecodeError:  # pragma: no cover - defensive
            user_lines.append(f"\n# Input:\n{task.input_data}")

    if tool_definitions:
        user_lines.append(
            "\nYou may call tools to help complete this task. "
            "To call a tool, respond with:\n"
            '{"tool_calls": [{"tool": "<name>", "arguments": {<args>}}]}\n'
            "When you have the final answer, respond with:\n"
            '{"summary": "...", "output": {...}, '
            '"confidence": <0-1>, "followup_actions": [...]}'
        )
    else:
        user_lines.append(
            "\nReturn a JSON object with keys: summary (str), output (object), "
            "confidence (number 0-1 optional), followup_actions (list[str] optional)."
        )

    return [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content="\n".join(user_lines)),
    ]


def append_tool_results(
    messages: list[ChatMessage],
    tool_calls: list[ToolCallRecord],
) -> list[ChatMessage]:
    """Append tool results to the conversation as an assistant + user pair.

    The assistant message announces which tools were called; the user
    message provides the results. This is the simplest approach that works
    across all providers (including those without native tool-call support).
    """
    if not tool_calls:
        return messages

    # Build a summary of what was called and what came back.
    call_lines: list[str] = []
    for tc in tool_calls:
        status_emoji = "✅" if tc.result.status == ToolResultStatus.SUCCESS else "❌"
        call_lines.append(f"- {status_emoji} `{tc.tool_name}` → {tc.result.status.value}")
        if tc.result.error:
            call_lines.append(f"  Error: {tc.result.error}")
        if tc.result.data is not None:
            data_str = json.dumps(tc.result.data, default=str)
            if len(data_str) > 500:
                data_str = data_str[:500] + "..."
            call_lines.append(f"  Result: {data_str}")

    assistant_content = "I called the following tools:\n" + "\n".join(call_lines)
    user_content = (
        "Here are the tool call results:\n\n"
        + json.dumps(
            [
                {
                    "tool": tc.tool_name,
                    "arguments": tc.arguments,
                    "status": tc.result.status.value,
                    "data": tc.result.data,
                    "error": tc.result.error,
                }
                for tc in tool_calls
            ],
            indent=2,
            default=str,
        )
        + "\n\nBased on these results, continue working. "
        "If you have the final answer, respond with the AgentResult JSON. "
        "Otherwise call more tools."
    )

    return messages + [
        ChatMessage(role="assistant", content=assistant_content),
        ChatMessage(role="user", content=user_content),
    ]


def _format_tool_definitions(definitions: list[dict]) -> str:
    """Format tool definitions as a readable block for the system prompt."""
    lines = ["\n## Available Tools\n"]
    for defn in definitions:
        params_str = ", ".join(
            f"{p['name']}: {p['type']}"
            + (" [required]" if p.get("required", True) else " [optional]")
            for p in defn.get("parameters", [])
        )
        danger = " ⚠️ DANGEROUS" if defn.get("dangerous") else ""
        lines.append(f"- **{defn['name']}**: {defn.get('description', '')}{danger}")
        if params_str:
            lines.append(f"  Parameters: {params_str}")
    lines.append(
        "\nTo use a tool, respond with: "
        '{"tool_calls": [{"tool": "<name>", "arguments": {<args>}}]}'
    )
    lines.append(
        "When finished, respond with: "
        '{"summary": "...", "output": {...}, "confidence": 0-1, "followup_actions": [...]}'
    )
    return "\n".join(lines)


def agent_is_executable(agent) -> bool:
    """Return whether an agent is eligible to run tasks."""
    return agent.status == AgentStatus.ACTIVE and bool(agent.provider and agent.model_name)
