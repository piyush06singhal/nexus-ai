"""HTTP API tests for workflow orchestration endpoints.

Uses the ``api_client`` fixture (SQLite-backed, ``get_db`` overridden).
The execute endpoint runs synchronously via ``workflow_execute_sync``.
"""

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _sync_execute(monkeypatch):
    """Turn on synchronous workflow execution for tests."""
    monkeypatch.setattr(settings, "workflow_execute_sync", True)


def _create_workflow(client, name="My Workflow", description="test"):
    resp = client.post("/api/v1/workflows", json={"name": name, "description": description})
    assert resp.status_code == 201
    return resp.json()


def _add_delay_step(client, workflow_id, name="s1"):
    resp = client.post(
        f"/api/v1/workflows/{workflow_id}/steps",
        json={
            "name": name,
            "step_type": "delay",
            "configuration": {"duration": 0},
            "order": 1,
        },
    )
    assert resp.status_code == 201
    return resp.json()


class TestWorkflowCRUD:
    def test_create_and_get(self, api_client):
        wf = _create_workflow(api_client)
        got = api_client.get(f"/api/v1/workflows/{wf['id']}").json()
        assert got["id"] == wf["id"]
        assert got["status"] == "draft"
        assert got["name"] == "My Workflow"

    def test_create_duplicate_conflicts(self, api_client):
        _create_workflow(api_client, name="dup")
        resp = api_client.post("/api/v1/workflows", json={"name": "dup"})
        assert resp.status_code == 409

    def test_list_workflows(self, api_client):
        _create_workflow(api_client, name="wf1")
        _create_workflow(api_client, name="wf2")
        data = api_client.get("/api/v1/workflows").json()
        assert len(data) == 2

    def test_update_workflow(self, api_client):
        wf = _create_workflow(api_client, name="orig")
        resp = api_client.patch(f"/api/v1/workflows/{wf['id']}", json={"name": "renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed"

    def test_delete_workflow(self, api_client):
        wf = _create_workflow(api_client)
        resp = api_client.delete(f"/api/v1/workflows/{wf['id']}")
        assert resp.status_code == 204
        assert api_client.get(f"/api/v1/workflows/{wf['id']}").status_code == 404

    def test_get_missing_returns_404(self, api_client):
        import uuid

        resp = api_client.get(f"/api/v1/workflows/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestWorkflowSteps:
    def test_add_and_list_steps(self, api_client):
        wf = _create_workflow(api_client)
        _add_delay_step(api_client, wf["id"], name="a")
        _add_delay_step(api_client, wf["id"], name="b")
        steps = api_client.get(f"/api/v1/workflows/{wf['id']}/steps").json()
        assert len(steps) == 2

    def test_delete_step(self, api_client):
        wf = _create_workflow(api_client)
        step = _add_delay_step(api_client, wf["id"])
        resp = api_client.delete(f"/api/v1/workflows/steps/{step['id']}")
        assert resp.status_code == 204
        steps = api_client.get(f"/api/v1/workflows/{wf['id']}/steps").json()
        assert len(steps) == 0


class TestWorkflowLifecycle:
    def test_activate_pause(self, api_client):
        wf = _create_workflow(api_client)
        _add_delay_step(api_client, wf["id"])
        resp = api_client.post(f"/api/v1/workflows/{wf['id']}/activate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"
        resp = api_client.post(f"/api/v1/workflows/{wf['id']}/pause")
        assert resp.json()["status"] == "paused"

    def test_activate_invalid_workflow_fails(self, api_client):
        # A step referencing an unknown tool makes activation fail validation.
        wf = _create_workflow(api_client)
        api_client.post(
            f"/api/v1/workflows/{wf['id']}/steps",
            json={
                "name": "bad",
                "step_type": "tool_action",
                "configuration": {"tool_name": "not_a_real_tool"},
            },
        )
        resp = api_client.post(f"/api/v1/workflows/{wf['id']}/activate")
        assert resp.status_code == 422

    def test_validate_endpoint(self, api_client):
        wf = _create_workflow(api_client)
        resp = api_client.get(f"/api/v1/workflows/{wf['id']}/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True


class TestWorkflowExecute:
    def test_execute_active_workflow(self, api_client):
        wf = _create_workflow(api_client)
        _add_delay_step(api_client, wf["id"])
        api_client.post(f"/api/v1/workflows/{wf['id']}/activate")
        resp = api_client.post(f"/api/v1/workflows/{wf['id']}/execute", json={})
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "completed"
        # Executions are listable.
        execs = api_client.get(f"/api/v1/workflows/{wf['id']}/executions").json()
        assert len(execs) == 1

    def test_execute_draft_workflow_rejected(self, api_client):
        wf = _create_workflow(api_client)
        _add_delay_step(api_client, wf["id"])
        resp = api_client.post(f"/api/v1/workflows/{wf['id']}/execute", json={})
        assert resp.status_code == 422

    def test_step_executions_listed(self, api_client):
        wf = _create_workflow(api_client)
        _add_delay_step(api_client, wf["id"])
        api_client.post(f"/api/v1/workflows/{wf['id']}/activate")
        execution = api_client.post(f"/api/v1/workflows/{wf['id']}/execute", json={}).json()
        steps = api_client.get(f"/api/v1/workflows/executions/{execution['id']}/steps").json()
        assert len(steps) == 1
        assert steps[0]["status"] == "completed"

    def test_cancel_queued_execution(self, api_client, db_engine):
        """A queued (not-yet-run) execution can be cancelled via the API."""
        wf = _create_workflow(api_client)
        _add_delay_step(api_client, wf["id"])
        api_client.post(f"/api/v1/workflows/{wf['id']}/activate")

        # Create a queued execution directly through the service/DB side.
        from uuid import UUID

        from sqlalchemy.orm import Session

        from app.services.workflow_service import WorkflowService

        with Session(bind=db_engine, expire_on_commit=False) as session:
            execution = WorkflowService(session).create_execution(
                UUID(wf["id"]), trigger_type="manual"
            )
            exec_id = str(execution.id)

        resp = api_client.post(f"/api/v1/workflows/executions/{exec_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_completed_execution_rejected(self, api_client):
        """A completed execution can no longer be cancelled."""
        wf = _create_workflow(api_client)
        _add_delay_step(api_client, wf["id"])
        api_client.post(f"/api/v1/workflows/{wf['id']}/activate")
        execution = api_client.post(f"/api/v1/workflows/{wf['id']}/execute", json={}).json()
        resp = api_client.post(f"/api/v1/workflows/executions/{execution['id']}/cancel")
        assert resp.status_code == 422


class TestWorkflowTriggers:
    def test_add_list_trigger(self, api_client):
        wf = _create_workflow(api_client)
        resp = api_client.post(
            f"/api/v1/workflows/{wf['id']}/triggers",
            json={"trigger_type": "schedule", "configuration": {"interval": 60}},
        )
        assert resp.status_code == 201
        triggers = api_client.get(f"/api/v1/workflows/{wf['id']}/triggers").json()
        assert len(triggers) == 1

    def test_delete_trigger(self, api_client):
        wf = _create_workflow(api_client)
        trigger = api_client.post(
            f"/api/v1/workflows/{wf['id']}/triggers",
            json={"trigger_type": "event", "configuration": {"event_name": "lead"}},
        ).json()
        assert api_client.delete(f"/api/v1/workflows/triggers/{trigger['id']}").status_code == 204
