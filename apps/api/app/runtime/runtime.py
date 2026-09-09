"""Agent runtime — the heart of Phase 1+2.

One agent, one task, one execution, one model, reliable persistence.
Phase 2 adds a tool-calling loop: the model can request tool calls,
the runtime executes them, feeds results back, and repeats until the
model returns a final AgentResult or the iteration limit is reached.

Pipeline (with tools):
    load_agent → validate_task → build_context (with tools)
    → [loop]: execute_model → if tool_calls → execute_tools → append results → repeat
    → parse_result → persist_execution → return_result

Pipeline (without tools, same as Phase 1):
    load_agent → validate_task → build_context → execute_model
    → parse_result → persist_execution → return_result
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.ai.interfaces import ModelProvider
from app.ai.providers.mock_provider import MockProvider
from app.ai.registry import get_provider
from app.ai.types import GenerationOptions
from app.core.errors import NotFoundError, ServiceUnavailableError, ValidationError
from app.core.logging import get_logger
from app.db.models.execution import AgentExecution
from app.runtime.context import agent_is_executable, append_tool_results, build_context
from app.schemas.runtime import AgentResult
from app.services.agent_service import AgentService
from app.services.execution_service import ExecutionService
from app.services.permission_service import PermissionService
from app.services.task_service import TaskService
from app.tools.executor import ToolExecutor
from app.tools.registry import get_tool_definitions
from app.tools.types import ToolCallRecord

logger = get_logger(__name__)


def _json_object(raw: str | None) -> dict[str, Any]:
    """Parse a stored JSON Text blob into a dict, tolerating None/invalid.

    Model and task payload columns (e.g. ``model_params``, ``input_data``) are
    persisted as JSON strings; this mirrors how ``task.input_data`` is read.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}

# Fallback pricing used to estimate cost when a provider doesn't supply it.
DEFAULT_PRICE_PER_1K = {"prompt": 0.0, "completion": 0.0}
PROVIDER_PRICES: dict[str, dict[str, float]] = {
    "openai": {"prompt": 0.0025, "completion": 0.0100},
    "anthropic": {"prompt": 0.0030, "completion": 0.0150},
}

# Maximum number of tool-calling iterations before the runtime gives up.
DEFAULT_MAX_TOOL_ITERATIONS = 10


class AgentRuntime:
    """Orchestrates a single deterministic agent task execution."""

    def __init__(
        self,
        *,
        agent_service: AgentService,
        task_service: TaskService,
        execution_service: ExecutionService,
        provider: ModelProvider | None = None,
        enable_tools: bool = True,
        max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
    ) -> None:
        self._agents = agent_service
        self._tasks = task_service
        self._executions = execution_service
        # A provider may be injected (tests); otherwise resolved per call.
        self._provider = provider
        self._enable_tools = enable_tools
        self._max_tool_iterations = max_tool_iterations

    def _resolve_provider(self, agent) -> ModelProvider:
        """Resolve the model provider for an agent.

        An explicitly injected provider (tests) always wins. Otherwise the
        provider is resolved from the agent's ``provider`` name via the
        registry. The mock provider additionally honors optional keys in
        ``agent.model_params`` so a scripted tool-call sequence can be driven
        end-to-end over the HTTP API: ``script`` (ordered list of responses) or
        ``reply`` (single fixed response).
        """
        if self._provider is not None:
            return self._provider

        if agent.provider == MockProvider.name:
            params = _json_object(agent.model_params)
            kwargs: dict[str, object] = {}
            script = params.get("script")
            if isinstance(script, list) and script:
                kwargs["script"] = [str(item) for item in script]
            elif "reply" in params:
                kwargs["reply"] = str(params["reply"])
            return MockProvider(**kwargs)

        return get_provider(agent.provider)

    def execute_task(self, task_id) -> AgentExecution:
        """Execute the given task with its assigned agent and persist the result.

        Returns the persisted :class:`AgentExecution` (succeeded or failed).
        """
        task = self._tasks.get(task_id)
        if task.assigned_agent_id is None:
            raise ValidationError("Task is not assigned to an agent")
        agent = self._agents.get(task.assigned_agent_id)

        if not agent_is_executable(agent):
            raise ValidationError(
                f"Agent {agent.name!r} is not executable (status must be active, "
                "provider and model_name are required)"
            )

        # Load or resolve the provider for this agent.
        provider = self._resolve_provider(agent)

        # Begin the execution record (running).
        input_payload = json.loads(task.input_data) if task.input_data else None
        execution = self._executions.begin(
            task_id=task.id, agent_id=agent.id, input_data=input_payload
        )
        self._tasks.mark_in_progress(task.id)

        options = GenerationOptions(
            model=agent.model_name,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )

        try:
            # Determine whether to use tool calling.
            tool_defs = get_tool_definitions() if self._enable_tools else None

            messages = build_context(agent, task, tool_definitions=tool_defs)
            started = datetime.now(UTC)
            all_tool_calls: list[ToolCallRecord] = []
            total_usage = None

            try:
                # --- Tool-calling loop ---
                for iteration in range(1, self._max_tool_iterations + 1):
                    model_response = provider.generate(messages, options=options)
                    raw = model_response.content

                    # Accumulate token usage.
                    if model_response.usage:
                        total_usage = self._accumulate_usage(total_usage, model_response.usage)

                    # Try to parse as tool call request first.
                    parsed = self._try_parse_json(raw)
                    if parsed is not None and "tool_calls" in parsed:
                        # Execute the requested tools.
                        tool_call_records = self._execute_tool_calls(
                            tool_calls_data=parsed["tool_calls"],
                            execution_id=execution.id,
                            agent_id=agent.id,
                            iteration=iteration,
                            db=self._executions._db,
                        )
                        all_tool_calls.extend(tool_call_records)

                        # Append results to context and continue the loop.
                        messages = append_tool_results(messages, tool_call_records)
                        continue

                    # Not a tool call — parse as final AgentResult.
                    result = AgentResult.model_validate(parsed)
                    break
                else:
                    # Exhausted all iterations without a final result.
                    self._executions.fail(
                        execution.id,
                        error=(
                            "Agent exceeded maximum tool-calling iterations "
                            f"({self._max_tool_iterations})"
                        ),
                        provider=agent.provider,
                        model_name=agent.model_name,
                    )
                    self._tasks.mark_failed(task.id)
                    raise ServiceUnavailableError(
                        f"Agent {agent.name!r} exceeded the maximum tool-calling "
                        f"iterations ({self._max_tool_iterations})."
                    )

            except (ValidationError, NotFoundError):
                self._executions.fail(execution.id, error="Execution validation failed.")
                self._tasks.mark_failed(task.id)
                raise

            except ServiceUnavailableError:
                raise

            except Exception as exc:
                self._executions.fail(
                    execution.id,
                    error=f"Could not produce a valid agent result: {exc}",
                    provider=agent.provider,
                    model_name=agent.model_name,
                )
                self._tasks.mark_failed(task.id)
                raise ServiceUnavailableError(
                    f"Agent {agent.name!r} returned an unparseable result."
                ) from exc

            latency_ms = (datetime.now(UTC) - started).total_seconds() * 1000.0
            estimate = self._estimate_from(total_usage, agent.provider)

            execution = self._executions.complete(
                execution.id,
                result=result,
                provider=agent.provider,
                model_name=model_response.model,
                usage=total_usage,
                latency_ms=latency_ms,
                estimated_cost=estimate,
            )
            self._tasks.mark_completed(task.id)
            return execution

        except (ValidationError, NotFoundError):
            if execution.status.value == "running":
                self._executions.fail(execution.id, error="Execution validation failed.")
                self._tasks.mark_failed(task.id)
            raise
        except ServiceUnavailableError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("execution_failed", extra={"task_id": str(task_id), "error": str(exc)})
            self._executions.fail(
                execution.id,
                error=str(exc),
                provider=agent.provider,
                model_name=agent.model_name,
            )
            self._tasks.mark_failed(task.id)
            raise ServiceUnavailableError(
                f"Agent {agent.name!r} failed while executing task {task.id}."
            ) from exc

    def _execute_tool_calls(
        self,
        *,
        tool_calls_data: list[dict],
        execution_id,
        agent_id,
        iteration: int,
        db,
    ) -> list[ToolCallRecord]:
        """Execute a batch of tool calls from the model's response."""
        permission_svc = PermissionService(db)
        perm_ctx = permission_svc.get_context(agent_id)
        executor = ToolExecutor(db)

        records: list[ToolCallRecord] = []
        for tc_data in tool_calls_data:
            tool_name = tc_data.get("tool", "")
            arguments = tc_data.get("arguments", {})
            record = executor.execute(
                tool_name=tool_name,
                arguments=arguments,
                execution_id=execution_id,
                agent_id=agent_id,
                permission_context=perm_ctx,
                iteration=iteration,
            )
            records.append(record)
        return records

    @staticmethod
    def _try_parse_json(text: str) -> dict | None:
        """Try to parse *text* as JSON. Returns None if it fails."""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _accumulate_usage(existing, new_usage):
        """Add new token usage to the running total."""
        if existing is None:
            return new_usage
        from app.ai.types import TokenUsage

        return TokenUsage(
            prompt_tokens=existing.prompt_tokens + new_usage.prompt_tokens,
            completion_tokens=existing.completion_tokens + new_usage.completion_tokens,
            total_tokens=existing.total_tokens + new_usage.total_tokens,
        )

    @staticmethod
    def _estimate_from(usage, provider_name: str) -> float:
        """Estimate USD cost of an execution from token usage."""
        if usage is None:
            return 0.0
        prices = PROVIDER_PRICES.get(provider_name, DEFAULT_PRICE_PER_1K)
        return (getattr(usage, "prompt_tokens", 0) or 0) / 1000.0 * prices["prompt"] + (
            getattr(usage, "completion_tokens", 0) or 0
        ) / 1000.0 * prices["completion"]

    def get_execution(self, execution_id) -> AgentExecution:
        return self._executions.get(execution_id)
