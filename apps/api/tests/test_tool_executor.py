"""Tests for the tool executor, permissions, and tool call persistence."""

from uuid import uuid4

from app.tools.executor import ToolExecutor
from app.tools.permissions import PermissionContext, check_permission
from app.tools.types import ToolResultStatus

# ---------------------------------------------------------------------------
# Permission system tests
# ---------------------------------------------------------------------------


class TestPermissions:
    def _make_tool_def(self, *, dangerous=False, name="test_tool"):
        from app.tools.types import ToolDefinition

        return ToolDefinition(name=name, description="test", dangerous=dangerous)

    def test_non_dangerous_always_allowed(self):
        ctx = PermissionContext(agent_id=uuid4())
        assert check_permission(self._make_tool_def(), ctx) is True

    def test_dangerous_denied_without_allowlist(self):
        ctx = PermissionContext(agent_id=uuid4())
        assert check_permission(self._make_tool_def(dangerous=True), ctx) is False

    def test_dangerous_allowed_when_in_allowlist(self):
        ctx = PermissionContext(agent_id=uuid4(), allowed_tools={"test_tool"})
        assert check_permission(self._make_tool_def(dangerous=True), ctx) is True

    def test_explicit_deny_overrides(self):
        ctx = PermissionContext(agent_id=uuid4(), denied_tools={"test_tool"})
        assert check_permission(self._make_tool_def(), ctx) is False

    def test_admin_bypass(self):
        ctx = PermissionContext(agent_id=uuid4(), has_admin=True)
        assert check_permission(self._make_tool_def(dangerous=True), ctx) is True

    def test_allowlist_restricts_non_dangerous(self):
        ctx = PermissionContext(agent_id=uuid4(), allowed_tools={"other_tool"})
        assert check_permission(self._make_tool_def(), ctx) is False


# ---------------------------------------------------------------------------
# Tool executor tests (with in-memory DB)
# ---------------------------------------------------------------------------


class TestToolExecutor:
    def setup_method(self):
        """Create an in-memory SQLite engine for each test."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from sqlalchemy.pool import StaticPool

        from app.db.session import Base

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(bind=self.engine, expire_on_commit=False)

    def teardown_method(self):
        self.db.close()

    def _make_ctx(self, **kwargs):
        return PermissionContext(agent_id=uuid4(), **kwargs)

    def test_execute_calculator(self):
        executor = ToolExecutor(self.db)
        ctx = self._make_ctx()
        record = executor.execute(
            tool_name="calculator",
            arguments={"expression": "2 + 2"},
            execution_id=uuid4(),
            agent_id=uuid4(),
            permission_context=ctx,
        )
        assert record.result.status == ToolResultStatus.SUCCESS
        assert record.result.data["result"] == 4.0
        assert record.tool_name == "calculator"
        assert record.iteration == 1

    def test_execute_unknown_tool_returns_error(self):
        executor = ToolExecutor(self.db)
        ctx = self._make_ctx()
        record = executor.execute(
            tool_name="nonexistent_tool",
            arguments={},
            execution_id=uuid4(),
            agent_id=uuid4(),
            permission_context=ctx,
        )
        assert record.result.status == ToolResultStatus.ERROR
        assert "not registered" in record.result.error

    def test_execute_permission_denied(self):
        executor = ToolExecutor(self.db)
        ctx = self._make_ctx(denied_tools={"calculator"})
        record = executor.execute(
            tool_name="calculator",
            arguments={"expression": "1 + 1"},
            execution_id=uuid4(),
            agent_id=uuid4(),
            permission_context=ctx,
        )
        assert record.result.status == ToolResultStatus.DENIED

    def test_execute_validates_arguments(self):
        executor = ToolExecutor(self.db)
        ctx = self._make_ctx()
        record = executor.execute(
            tool_name="calculator",
            arguments={},  # missing required 'expression'
            execution_id=uuid4(),
            agent_id=uuid4(),
            permission_context=ctx,
        )
        assert record.result.status == ToolResultStatus.ERROR
        assert "validation failed" in record.result.error.lower()

    def test_tool_call_persisted_to_db(self):
        executor = ToolExecutor(self.db)
        ctx = self._make_ctx()
        exec_id = uuid4()
        record = executor.execute(
            tool_name="calculator",
            arguments={"expression": "5 * 5"},
            execution_id=exec_id,
            agent_id=uuid4(),
            permission_context=ctx,
        )
        # Verify the tool call was persisted.
        from app.db.models.tool_call import ToolCallRecord

        orm = self.db.get(ToolCallRecord, record.id)
        assert orm is not None
        assert orm.execution_id == exec_id
        assert orm.tool_name == "calculator"
        assert orm.result_status.value == "success"

    def test_iteration_tracking(self):
        executor = ToolExecutor(self.db)
        ctx = self._make_ctx()
        record = executor.execute(
            tool_name="calculator",
            arguments={"expression": "1 + 1"},
            execution_id=uuid4(),
            agent_id=uuid4(),
            permission_context=ctx,
            iteration=3,
        )
        assert record.iteration == 3

    def test_max_output_bytes_enforced(self, monkeypatch):
        """max_output_bytes is enforced in-process: oversized tool data is
        discarded and the result is marked DENIED."""
        from app.security import tool_security
        from app.security.tool_security import ToolSandbox, ToolSecurityPolicy

        monkeypatch.setitem(
            tool_security._SANDBOX_TEMPLATES,
            "tiny",
            ToolSandbox(tool_name="*", timeout_seconds=30.0, max_output_bytes=10),
        )
        policy = ToolSecurityPolicy(default_sandbox="tiny")
        executor = ToolExecutor(self.db, tool_policy=policy)
        ctx = self._make_ctx()
        record = executor.execute(
            tool_name="calculator",
            arguments={"expression": "2 + 2"},
            execution_id=uuid4(),
            agent_id=uuid4(),
            permission_context=ctx,
        )
        # The JSON output of {"result": 4.0} is ~15 bytes, exceeding the limit.
        assert record.result.status == ToolResultStatus.DENIED
        assert "exceeded the sandbox limit" in record.result.error
        assert record.result.data is None
