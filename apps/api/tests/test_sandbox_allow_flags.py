"""Tests for ToolSandbox allow_* flag enforcement (executor step 3.6)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.tools.base import BaseTool
from app.tools.executor import ToolExecutor
from app.tools.permissions import PermissionContext
from app.tools.registry import register_tool, unregister_tool
from app.tools.types import (
    ToolCallRecord,
    ToolDefinition,
    ToolParameter,
    ToolResult,
    ToolResultStatus,
)

# -- Helpers ----------------------------------------------------------------


class _DummyTool(BaseTool):
    """Minimal BaseTool whose capability declarations are configurable."""

    def __init__(
        self,
        *,
        requires_filesystem: bool = False,
        requires_network: bool = False,
        requires_process: bool = False,
    ) -> None:
        self._requires = {
            "requires_filesystem_access": requires_filesystem,
            "requires_network_access": requires_network,
            "requires_process_access": requires_process,
        }

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="dummy_sandbox_tool",
            description="a test tool for sandbox allow-flag tests",
            parameters=[ToolParameter(name="msg", type="string", description="input")],
            timeout_seconds=5.0,
            **self._requires,
        )

    def validate_arguments(self, args: dict) -> dict:
        return args

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            data={"echo": kwargs.get("msg", "")},
        )


def _setup_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(bind=engine, expire_on_commit=False)


@contextmanager
def _sandbox_context(
    *,
    allow_filesystem: bool = True,
    allow_network: bool = True,
    allow_process: bool = True,
):
    """Yield (executor, db_session) with the sandbox allow-flags set.

    Registers a ``_DummyTool`` in the real registry and patches
    ``guard_tool_call`` so the sandbox uses the requested allow-flags.
    Cleans up both the patch and the registry entry on exit.
    """
    from app.security.tool_security import ToolSandbox

    dummy = _DummyTool(
        requires_filesystem=False,
        requires_network=False,
        requires_process=False,
    )

    def _fake_guard(tool_name, arguments, timeout_seconds, context_kind, policy):
        sandbox = ToolSandbox(
            tool_name=tool_name,
            timeout_seconds=timeout_seconds,
            max_output_bytes=1024 * 1024,
            allow_filesystem=allow_filesystem,
            allow_network=allow_network,
            allow_process=allow_process,
        )
        return sandbox, arguments

    db = _setup_db()
    register_tool(dummy)
    patcher = patch("app.tools.executor.guard_tool_call", side_effect=_fake_guard)
    patcher.start()

    executor = ToolExecutor(db=db)
    try:
        yield executor, db
    finally:
        patcher.stop()
        unregister_tool("dummy_sandbox_tool")
        db.close()


def _execute_with_dummy(
    executor: ToolExecutor,
    dummy: _DummyTool,
    *,
    allow_filesystem: bool = True,
    allow_network: bool = True,
    allow_process: bool = True,
) -> ToolCallRecord:
    """Execute a dummy tool through the executor with the given sandbox allow-flags.

    Registers the tool, patches guard_tool_call, runs execute(), cleans up.
    """
    from app.security.tool_security import ToolSandbox

    def _fake_guard(tool_name, arguments, timeout_seconds, context_kind, policy):
        sandbox = ToolSandbox(
            tool_name=tool_name,
            timeout_seconds=timeout_seconds,
            max_output_bytes=1024 * 1024,
            allow_filesystem=allow_filesystem,
            allow_network=allow_network,
            allow_process=allow_process,
        )
        return sandbox, arguments

    register_tool(dummy)
    try:
        with patch("app.tools.executor.guard_tool_call", side_effect=_fake_guard):
            return executor.execute(
                tool_name=dummy.definition.name,
                arguments={"msg": "hello"},
                execution_id=uuid4(),
                agent_id=uuid4(),
                permission_context=PermissionContext(agent_id=uuid4()),
            )
    finally:
        unregister_tool(dummy.definition.name)


# -- Tests ------------------------------------------------------------------


class TestSandboxAllowFlags:
    """Step 3.6: deny tools whose capabilities exceed the sandbox budget."""

    def setup_method(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = Session(bind=engine, expire_on_commit=False)

    def teardown_method(self):
        self.db.close()

    @pytest.mark.parametrize(
        ("tool_kwargs", "allow_kwargs", "expect_denied"),
        [
            (dict(requires_network=True), dict(allow_network=False), True),
            (dict(requires_network=True), dict(allow_network=True), False),
            (dict(requires_filesystem=True), dict(allow_filesystem=False), True),
            (dict(requires_filesystem=True), dict(allow_filesystem=True), False),
            (dict(requires_process=True), dict(allow_process=False), True),
            (dict(requires_process=True), dict(allow_process=True), False),
            # Multiple capabilities: deny if ANY is blocked
            (
                dict(requires_network=True, requires_filesystem=True),
                dict(allow_network=True, allow_filesystem=False),
                True,
            ),
            (
                dict(requires_network=True, requires_filesystem=True),
                dict(allow_network=True, allow_filesystem=True),
                False,
            ),
        ],
        ids=[
            "net-denied",
            "net-allowed",
            "fs-denied",
            "fs-allowed",
            "proc-denied",
            "proc-allowed",
            "multi-deny-one-blocked",
            "multi-all-allowed",
        ],
    )
    def test_allow_flag_enforcement(self, tool_kwargs, allow_kwargs, expect_denied):
        dummy = _DummyTool(**tool_kwargs)
        executor = ToolExecutor(db=self.db)

        record = _execute_with_dummy(
            executor,
            dummy,
            **allow_kwargs,
        )

        if expect_denied:
            assert record.result.status == ToolResultStatus.DENIED
            assert "sandbox denies" in record.result.error.lower()
        else:
            assert record.result.status == ToolResultStatus.SUCCESS
            assert record.result.error is None

    def test_pure_computation_tool_always_passes(self):
        """Existing tools (all requires_* default False) are unaffected by the gate."""
        dummy = _DummyTool()  # all requires_* default False
        executor = ToolExecutor(db=self.db)

        record = _execute_with_dummy(
            executor,
            dummy,
            allow_filesystem=False,
            allow_network=False,
            allow_process=False,
        )

        assert record.result.status == ToolResultStatus.SUCCESS
