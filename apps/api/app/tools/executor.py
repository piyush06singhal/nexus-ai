"""Tool executor.

Runs tools safely with validation, authorization, timeout enforcement, and
result persistence. The executor is the single entry point between the
agent runtime and individual tool instances.

Flow:
    1. Resolve tool from registry.
    2. Validate arguments against the tool's parameter schema.
    3. Check permissions.
    4. Execute the tool (with timeout).
    5. Persist the tool call record.
    6. Return the result to the runtime.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.db.models.tool_call import ToolCallRecord as ToolCallORM
from app.security.tool_security import (
    ToolSecurityError,
    ToolSecurityPolicy,
    guard_tool_call,
)
from app.tools.permissions import PermissionContext, check_permission
from app.tools.registry import get_tool
from app.tools.types import ToolCallRecord, ToolResult, ToolResultStatus

logger = get_logger(__name__)

# Module-level thread pool for tool execution with timeout.
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool-exec")


class ToolExecutor:
    """Executes tools with safety checks and persistence.

    Args:
        db: SQLAlchemy session for persisting tool call records.
        timeout_seconds: Default timeout for tools that don't specify one.
    """

    DEFAULT_TIMEOUT: float = 30.0

    def __init__(
        self,
        db,
        *,
        timeout_seconds: float | None = None,
        tool_policy: ToolSecurityPolicy | None = None,
        context_kind: str = "agent",
    ) -> None:
        self._db = db
        self._default_timeout = timeout_seconds or self.DEFAULT_TIMEOUT
        self._tool_policy = tool_policy or ToolSecurityPolicy()
        self._context_kind = context_kind

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        execution_id: UUID,
        agent_id: UUID,
        permission_context: PermissionContext,
        iteration: int = 1,
    ) -> ToolCallRecord:
        """Execute a single tool call.

        Returns a :class:`ToolCallRecord` with the result. The record is
        also persisted to the ``tool_calls`` table.
        """
        # 1. Resolve tool
        try:
            tool = get_tool(tool_name)
        except Exception:
            result = ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Tool '{tool_name}' is not registered",
            )
            record = self._persist(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                execution_id=execution_id,
                iteration=iteration,
            )
            return record
        tool_def = tool.definition

        # 2. Validate arguments
        try:
            validated_args = tool.validate_arguments(arguments)
        except ValueError as exc:
            result = ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Argument validation failed: {exc}",
            )
            record = self._persist(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                execution_id=execution_id,
                iteration=iteration,
            )
            return record

        # 3. Check permissions
        if not check_permission(tool_def, permission_context):
            result = ToolResult(
                status=ToolResultStatus.DENIED,
                error=f"Agent does not have permission to execute tool '{tool_name}'",
            )
            record = self._persist(
                tool_name=tool_name,
                arguments=validated_args,
                result=result,
                execution_id=execution_id,
                iteration=iteration,
            )
            return record

        # 3.5 Tool-security gate (Phase 11): deny-list, per-tool budget,
        # context check, and the self-escalation guard — all before execution.
        try:
            sandbox, arguments = guard_tool_call(
                tool_name=tool_name,
                arguments=validated_args,
                timeout_seconds=tool_def.timeout_seconds or self._default_timeout,
                context_kind=self._context_kind,
                policy=self._tool_policy,
            )
        except ToolSecurityError as exc:
            result = ToolResult(
                status=ToolResultStatus.DENIED,
                error=f"Tool security refused: {exc}",
            )
            record = self._persist(
                tool_name=tool_name,
                arguments=validated_args,
                result=result,
                execution_id=execution_id,
                iteration=iteration,
            )
            logger.warning(
                "tool_security_denied",
                extra={
                    "tool": tool_name,
                    "reason": str(exc),
                    "execution_id": str(execution_id),
                },
            )
            return record

        # 4. Execute with timeout
        timeout = sandbox.timeout_seconds
        start = time.monotonic()
        try:
            future = _POOL.submit(tool.execute, **validated_args)
            tool_result = future.result(timeout=timeout)
        except FuturesTimeoutError:
            elapsed_ms = (time.monotonic() - start) * 1000
            tool_result = ToolResult(
                status=ToolResultStatus.TIMEOUT,
                error=f"Tool '{tool_name}' timed out after {timeout:.1f}s",
                execution_time_ms=elapsed_ms,
            )
            logger.warning(
                "tool_timeout",
                extra={"tool": tool_name, "timeout": timeout, "execution_id": str(execution_id)},
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            tool_result = ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Tool '{tool_name}' raised: {exc}",
                execution_time_ms=elapsed_ms,
            )
            logger.exception(
                "tool_execution_error",
                extra={"tool": tool_name, "execution_id": str(execution_id)},
            )

        if tool_result.execution_time_ms is None:
            tool_result.execution_time_ms = (time.monotonic() - start) * 1000

        # 4.5 Enforce output size limit (in-process guard — the first kernelless
        #     but real enforcement of the declared sandbox budget).
        if sandbox.max_output_bytes > 0 and tool_result.data is not None:
            output_bytes = len(json.dumps(tool_result.data, default=str).encode("utf-8"))
            if output_bytes > sandbox.max_output_bytes:
                logger.warning(
                    "tool_output_truncated",
                    extra={
                        "tool": tool_name,
                        "output_bytes": output_bytes,
                        "max_bytes": sandbox.max_output_bytes,
                        "execution_id": str(execution_id),
                    },
                )
                tool_result.data = None
                tool_result.error = (
                    f"Tool output ({output_bytes:,} bytes) exceeded the sandbox "
                    f"limit ({sandbox.max_output_bytes:,} bytes) and was discarded"
                )
                tool_result.status = ToolResultStatus.DENIED

        # 5. Persist
        record = self._persist(
            tool_name=tool_name,
            arguments=validated_args,
            result=tool_result,
            execution_id=execution_id,
            iteration=iteration,
        )

        return record

    def _persist(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
        execution_id: UUID,
        iteration: int,
    ) -> ToolCallRecord:
        """Persist a tool call record to the DB and return a transient record."""
        orm = ToolCallORM(
            execution_id=execution_id,
            tool_name=tool_name,
            arguments=json.dumps(arguments, default=str),
            result_status=result.status.value,
            result_data=json.dumps(result.data, default=str) if result.data is not None else None,
            result_error=result.error,
            execution_time_ms=result.execution_time_ms,
            iteration=iteration,
        )
        self._db.add(orm)
        self._db.commit()
        self._db.refresh(orm)

        return ToolCallRecord(
            id=orm.id,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            iteration=iteration,
        )
