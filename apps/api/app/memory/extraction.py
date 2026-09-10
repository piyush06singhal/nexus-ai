"""Memory extraction from agent executions.

After a task completes, the runtime may derive memories so the agent can recall
the experience later. This module turns an :class:`AgentExecution` into one or
more :class:`Memory` records of varied types:

- an **episodic** memory summarizing what happened;
- **semantic** memories distilled from the structured output when confident;
- a **procedural** memory when the execution involved tools.

Importance is derived from signal in the execution (confidence, tool usage,
work done) so that richer executions produce more significant memories.
"""

from __future__ import annotations

import json
from uuid import UUID

from app.db.models.execution import AgentExecution, ExecutionStatus
from app.db.models.memory import (
    Memory,
    MemoryOwnerType,
    MemorySourceType,
    MemoryStatus,
    MemoryType,
)
from app.memory.embedding import EmbeddingProvider


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):  # pragma: no cover - defensive
        return None


def _task_title(execution: AgentExecution) -> str:
    """Best-effort task title from metadata_json (may be absent)."""
    meta = _loads(execution.metadata_json) or {}
    if not isinstance(meta, dict):
        return ""
    return str(meta.get("task_title", "")) if meta.get("task_title") else ""


def _result_output(execution: AgentExecution) -> dict:
    """The AgentResult dict (summary/output/confidence/...) if it succeeded."""
    if execution.status != ExecutionStatus.SUCCEEDED:
        return {}
    loaded = _loads(execution.output_data)
    return loaded if isinstance(loaded, dict) else {}


async def extract_memories_from_execution(
    execution: AgentExecution,
    *,
    namespace: str,
    agent_id: UUID,
    embedding_provider: EmbeddingProvider | None = None,
    used_tools: list[str] | None = None,
) -> list[Memory]:
    """Derive memory records from a completed (or failed) execution.

    Failed executions yield a single low-importance episodic memory. Succeeded
    executions yield richer episodic + semantic (+ procedural) memories. The
    returned records are transient ORM objects; the caller persists them.
    """
    memories: list[Memory] = []
    common = {
        "namespace": namespace,
        "owner_type": MemoryOwnerType.AGENT,
        "owner_id": agent_id,
        "source_type": MemorySourceType.EXECUTION,
        "source_id": execution.id,
        "status": MemoryStatus.ACTIVE,
    }

    succeeded = execution.status == ExecutionStatus.SUCCEEDED
    output = _result_output(execution)
    confidence = _confidence(output, succeeded)

    # Episodic memory summarizing the experience.
    episodic = Memory(
        **common,
        type=MemoryType.EPISODIC,
        content=_episodic_content(execution, output, succeeded),
        summary=f"Execution {str(execution.id)[:8]}",
        importance=_importance(execution, succeeded, bool(output)),
        confidence=confidence,
        metadata_json=json.dumps(
            {
                "status": execution.status.value,
                "provider": execution.provider,
                "model_name": execution.model_name,
                "total_tokens": execution.total_tokens,
                "error": execution.error,
            }
        ),
    )
    memories.append(episodic)

    if succeeded and output:
        # Semantic memory from the structured result.
        semantic_text = _semantic_content(output)
        if semantic_text:
            memories.append(
                Memory(
                    **common,
                    type=MemoryType.SEMANTIC,
                    content=semantic_text,
                    summary=(output.get("summary") or "Semantic fact")[:256],
                    importance=min(episodic.importance + 0.1, 1.0),
                    confidence=output.get("confidence", 1.0)
                    if isinstance(output.get("confidence", 1.0), (int, float))
                    else 1.0,
                )
            )

        # Procedural memory when tools were involved.
        if used_tools:
            memories.append(
                Memory(
                    **common,
                    type=MemoryType.PROCEDURAL,
                    content=_procedural_content(used_tools),
                    summary="Tool usage pattern",
                    importance=min(episodic.importance + 0.15, 1.0),
                    confidence=confidence,
                )
            )
        elif _mentions_tools(output):
            memories.append(
                Memory(
                    **common,
                    type=MemoryType.PROCEDURAL,
                    content=_procedural_descriptive(output),
                    summary="Tool usage pattern",
                    importance=min(episodic.importance + 0.1, 1.0),
                    confidence=confidence,
                )
            )

    # Attach embeddings when a provider is configured.
    if embedding_provider is not None:
        texts = [(m.summary or "") + " " + m.content[:200] for m in memories]
        try:
            vectors = await embedding_provider.embed(texts)
        except Exception:  # pragma: no cover - defensive
            vectors = []
        for memory, vector in zip(memories, vectors, strict=True):
            memory.embedding = json.dumps(vector)

    return memories


def _episodic_content(execution: AgentExecution, output: dict, succeeded: bool) -> str:
    title = _task_title(execution)
    base = (
        f"Agent executed task{' ' + title if title else ''} "
        f"using {execution.total_tokens or 0} tokens."
    )
    if succeeded:
        summary = output.get("summary")
        return base + f" Result: {summary}" if summary else base
    return base + f" Failed: {execution.error or 'unknown error'}"


def _semantic_content(output: dict) -> str:
    """Flatten the AgentResult into statement-style semantic lines."""
    summary = output.get("summary")
    result = output.get("output")
    pieces: list[str] = []
    if summary:
        pieces.append(f"Task summary: {summary}")
    if isinstance(result, dict):
        for key, value in result.items():
            if isinstance(value, (str, int, float, bool)):
                pieces.append(f"{key}: {value}")
    return "\n".join(pieces)


def _mentions_tools(output: dict) -> bool:
    followups = output.get("followup_actions")
    return isinstance(followups, list) and any(
        isinstance(f, str) and "tool" in f.lower() for f in followups
    )


def _procedural_content(used_tools: list[str]) -> str:
    return "Used tools: " + ", ".join(used_tools)


def _procedural_descriptive(output: dict) -> str:
    followups = output.get("followup_actions")
    if isinstance(followups, list):
        tools = [f for f in followups if isinstance(f, str) and "tool" in f.lower()]
        if tools:
            return "Tool usage: " + "; ".join(tools)
    return "Follow-up tool actions were indicated."


def _importance(execution: AgentExecution, succeeded: bool, has_output: bool) -> float:
    score = 0.4
    if succeeded:
        score += 0.2
    if has_output:
        score += 0.15
    if execution.total_tokens and execution.total_tokens > 1000:
        score += 0.1
    return min(score, 1.0)


def _confidence(output: dict, succeeded: bool) -> float:
    if not succeeded:
        return 0.0
    conf = output.get("confidence")
    if isinstance(conf, (int, float)) and 0 <= conf <= 1:
        return float(conf)
    return 1.0
