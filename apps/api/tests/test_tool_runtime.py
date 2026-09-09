"""Tests for the AgentRuntime with tool calling enabled.

Exercises the full tool-calling loop: model returns tool_calls →
runtime executes them → feeds results back → model returns final result.
"""

import json
from uuid import uuid4

import pytest

from app.ai.providers.mock_provider import MockProvider
from app.ai.types import TokenUsage
from app.core.errors import ServiceUnavailableError
from app.db.models.agent import AgentStatus
from app.db.models.execution import ExecutionStatus
from app.db.models.tool_call import ToolCallRecord as ToolCallORM
from app.runtime.runtime import AgentRuntime
from app.schemas.agent import AgentCreate
from app.schemas.task import TaskCreate
from app.services.agent_service import AgentService
from app.services.execution_service import ExecutionService
from app.services.task_service import TaskService

# A tool-call response: the model asks to use the calculator.
TOOL_CALL_RESPONSE = json.dumps(
    {"tool_calls": [{"tool": "calculator", "arguments": {"expression": "2 + 3"}}]}
)

# A final AgentResult response.
FINAL_RESPONSE = json.dumps(
    {
        "summary": "Calculated 2+3=5",
        "output": {"result": 5},
        "confidence": 0.99,
    }
)


def _build_runtime(db, provider, *, enable_tools=True, max_iter=5):
    return AgentRuntime(
        agent_service=AgentService(db),
        task_service=TaskService(db),
        execution_service=ExecutionService(db),
        provider=provider,
        enable_tools=enable_tools,
        max_tool_iterations=max_iter,
    )


def _seed_agent_and_task(db):
    agent = AgentService(db).create(
        AgentCreate(
            name=f"agent-{uuid4().hex[:8]}",
            status=AgentStatus.ACTIVE,
            provider="mock",
            model_name="mock-model",
        )
    )
    task = TaskService(db).create(
        TaskCreate(title="Do math", input_data={"x": 10})
    )
    TaskService(db).assign(task.id, agent.id)
    return agent, task


class TestToolCallingLoop:
    def test_direct_result_without_tool_call(self, db):
        """Model returns AgentResult directly (no tools needed)."""
        agent, task = _seed_agent_and_task(db)
        provider = MockProvider(reply=FINAL_RESPONSE)
        runtime = _build_runtime(db, provider, enable_tools=True)

        execution = runtime.execute_task(task.id)
        assert execution.status == ExecutionStatus.SUCCEEDED
        assert "Calculated" in execution.output_data

    def test_tool_call_then_final_result(self, db):
        """Model requests a tool, gets the result, then returns final answer."""
        agent, task = _seed_agent_and_task(db)
        # First call: tool request. Second call: final result.
        provider = MockProvider(reply=TOOL_CALL_RESPONSE)
        # Override generate to return different things on successive calls.
        call_count = 0
        original_generate = provider.generate

        def sequenced_generate(messages, *, options=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_generate(messages, options=options)
            # Second call: return final result.
            from app.ai.types import ModelResponse

            return ModelResponse(
                content=FINAL_RESPONSE,
                model="mock-model",
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
            )

        provider.generate = sequenced_generate  # type: ignore[assignment]
        runtime = _build_runtime(db, provider, enable_tools=True)

        execution = runtime.execute_task(task.id)
        assert execution.status == ExecutionStatus.SUCCEEDED
        assert execution.total_tokens == 45  # 15 + 30

        # Verify tool calls were persisted.
        tool_calls = db.query(ToolCallORM).filter(
            ToolCallORM.execution_id == execution.id
        ).all()
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "calculator"
        assert tool_calls[0].result_status.value == "success"

    def test_tool_call_execution_error_continues(self, db):
        """If a tool call fails, the runtime feeds the error back and continues."""
        agent, task = _seed_agent_and_task(db)
        # First call: tool request for unknown tool.
        bad_tool_call = json.dumps(
            {"tool_calls": [{"tool": "no_such_tool", "arguments": {}}]}
        )
        provider = MockProvider(reply=bad_tool_call)
        call_count = 0
        original_generate = provider.generate

        def sequenced_generate(messages, *, options=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_generate(messages, options=options)
            from app.ai.types import ModelResponse

            return ModelResponse(
                content=FINAL_RESPONSE,
                model="mock-model",
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        provider.generate = sequenced_generate  # type: ignore[assignment]
        runtime = _build_runtime(db, provider, enable_tools=True)

        execution = runtime.execute_task(task.id)
        assert execution.status == ExecutionStatus.SUCCEEDED
        # The tool call should have a "error" status.
        tool_calls = db.query(ToolCallORM).filter(
            ToolCallORM.execution_id == execution.id
        ).all()
        assert len(tool_calls) == 1
        assert tool_calls[0].result_status.value == "error"

    def test_max_iterations_exceeded(self, db):
        """Runtime fails if the model keeps requesting tools without finishing."""
        agent, task = _seed_agent_and_task(db)
        # Always return tool calls, never a final result.
        provider = MockProvider(reply=TOOL_CALL_RESPONSE)
        runtime = _build_runtime(db, provider, enable_tools=True, max_iter=2)

        with pytest.raises(ServiceUnavailableError, match="maximum"):
            runtime.execute_task(task.id)

        exec_svc = ExecutionService(db)
        executions = exec_svc.list_by_task(task.id)
        assert len(executions) == 1
        assert executions[0].status == ExecutionStatus.FAILED

    def test_tools_disabled_skips_loop(self, db):
        """When enable_tools=False, the runtime behaves like Phase 1."""
        agent, task = _seed_agent_and_task(db)
        provider = MockProvider(reply=FINAL_RESPONSE)
        runtime = _build_runtime(db, provider, enable_tools=False)

        execution = runtime.execute_task(task.id)
        assert execution.status == ExecutionStatus.SUCCEEDED

    def test_multiple_tool_calls_in_one_response(self, db):
        """Model requests multiple tools in a single response."""
        agent, task = _seed_agent_and_task(db)
        multi_call = json.dumps(
            {
                "tool_calls": [
                    {"tool": "calculator", "arguments": {"expression": "1 + 1"}},
                    {"tool": "datetime", "arguments": {"action": "now"}},
                ]
            }
        )
        provider = MockProvider(reply=multi_call)
        call_count = 0
        original_generate = provider.generate

        def sequenced_generate(messages, *, options=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_generate(messages, options=options)
            from app.ai.types import ModelResponse

            return ModelResponse(
                content=FINAL_RESPONSE,
                model="mock-model",
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        provider.generate = sequenced_generate  # type: ignore[assignment]
        runtime = _build_runtime(db, provider, enable_tools=True)

        execution = runtime.execute_task(task.id)
        assert execution.status == ExecutionStatus.SUCCEEDED

        tool_calls = db.query(ToolCallORM).filter(
            ToolCallORM.execution_id == execution.id
        ).all()
        assert len(tool_calls) == 2
        tool_names = {tc.tool_name for tc in tool_calls}
        assert tool_names == {"calculator", "datetime"}

    def test_malformed_tool_call_json_falls_through_to_result(self, db):
        """If model returns non-JSON, it's parsed as AgentResult (may fail)."""
        agent, task = _seed_agent_and_task(db)
        provider = MockProvider(reply="not json at all")
        runtime = _build_runtime(db, provider, enable_tools=True)

        with pytest.raises(ServiceUnavailableError):
            runtime.execute_task(task.id)

    def test_scripted_mock_in_model_params_drives_tool_loop(self, db):
        """A scripted mock configured via agent.model_params runs the tool
        loop and persists a tool_calls row — no provider injection needed.

        This is the same path a live HTTP execution takes: the runtime builds
        the MockProvider from the agent's stored model_params.
        """
        agent = AgentService(db).create(
            AgentCreate(
                name=f"scripted-agent-{uuid4().hex[:8]}",
                status=AgentStatus.ACTIVE,
                provider="mock",
                model_name="mock-model",
                model_params={
                    "script": [
                        '{"tool_calls": [{"tool": "calculator", '
                        '"arguments": {"expression": "9 * 9"}}]}',
                        '{"summary": "computed", "output": {"result": 81}}',
                    ]
                },
            )
        )
        task = TaskService(db).create(TaskCreate(title="Use the calculator"))
        TaskService(db).assign(task.id, agent.id)

        runtime = _build_runtime(db, provider=None, enable_tools=True)
        execution = runtime.execute_task(task.id)

        assert execution.status == ExecutionStatus.SUCCEEDED
        # The runtime executed the requested tool and persisted it.
        tool_calls = db.query(ToolCallORM).filter(
            ToolCallORM.execution_id == execution.id
        ).all()
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "calculator"
        assert tool_calls[0].result_status.value == "success"
        output = json.loads(execution.output_data)
        assert output["output"]["result"] == 81
        assert output["summary"] == "computed"
