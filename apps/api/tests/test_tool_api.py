"""Tests for the tools and tool-calls API endpoints."""

from uuid import uuid4


class TestToolsAPI:
    def test_list_tools(self, api_client):
        response = api_client.get("/api/v1/tools")
        assert response.status_code == 200
        tools = response.json()
        assert isinstance(tools, list)
        assert len(tools) >= 4
        names = [t["name"] for t in tools]
        assert "calculator" in names
        assert "datetime" in names
        assert "text_utils" in names
        assert "json_utils" in names

    def test_get_tool_by_name(self, api_client):
        response = api_client.get("/api/v1/tools/calculator")
        assert response.status_code == 200
        tool = response.json()
        assert tool["name"] == "calculator"
        assert "parameters" in tool
        assert len(tool["parameters"]) == 1

    def test_get_tool_not_found(self, api_client):
        response = api_client.get("/api/v1/tools/nonexistent")
        assert response.status_code == 404

    def test_list_tool_calls_empty(self, api_client):
        """Tool calls for a nonexistent execution should be empty."""
        fake_id = str(uuid4())
        response = api_client.get(f"/api/v1/tools/calls/{fake_id}")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_tool_calls_invalid_uuid(self, api_client):
        response = api_client.get("/api/v1/tools/calls/not-a-uuid")
        assert response.status_code == 422

    def test_tool_call_api_with_persisted_record(self, db_engine, api_client):
        """Create a tool call via the executor, then fetch it via the API."""
        from sqlalchemy.orm import Session

        from app.tools.executor import ToolExecutor
        from app.tools.permissions import PermissionContext

        with Session(bind=db_engine, expire_on_commit=False) as db:
            exec_id = uuid4()
            agent_id = uuid4()
            executor = ToolExecutor(db)
            ctx = PermissionContext(agent_id=agent_id)
            executor.execute(
                tool_name="calculator",
                arguments={"expression": "6 * 7"},
                execution_id=exec_id,
                agent_id=agent_id,
                permission_context=ctx,
            )

            response = api_client.get(f"/api/v1/tools/calls/{exec_id}")
            assert response.status_code == 200
            calls = response.json()
            assert len(calls) == 1
            assert calls[0]["tool_name"] == "calculator"
            assert calls[0]["result_status"] == "success"
            assert calls[0]["arguments"]["expression"] == "6 * 7"
