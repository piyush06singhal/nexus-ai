"""End-to-end test of the full agent execution lifecycle via the public API.

Create Agent → assign Task → Execute → Persist → Retrieve → Verify.

Uses an active agent configured with ``provider="mock"`` so the runtime
resolves the registered MockProvider and produces a deterministic result
without any network call or API key.
"""


def test_full_execution_lifecycle(api_client):
    # 1. Create an active mock agent.
    agent_resp = api_client.post(
        "/api/v1/agents",
        json={
            "name": "e2e-analyst",
            "role": "analyst",
            "status": "active",
            "provider": "mock",
            "model_name": "mock-model",
            "system_prompt": "Always report metrics.",
        },
    )
    assert agent_resp.status_code == 201, agent_resp.text
    agent = agent_resp.json()

    # 2. Create a task with input data.
    task_resp = api_client.post(
        "/api/v1/tasks",
        json={"title": "Summarize Q1", "input_data": {"quarter": "Q1", "region": "APAC"}},
    )
    assert task_resp.status_code == 201
    task = task_resp.json()

    # 3. Assign the task to the agent.
    assign_resp = api_client.post(
        f"/api/v1/tasks/{task['id']}/assign", json={"agent_id": agent["id"]}
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["status"] == "queued"

    # 4. Execute the task through the runtime.
    exec_resp = api_client.post(f"/api/v1/tasks/{task['id']}/execute")
    assert exec_resp.status_code == 200, exec_resp.text
    execution = exec_resp.json()

    # 5. Verify the persisted execution record.
    assert execution["status"] == "succeeded"
    assert execution["agent_id"] == agent["id"]
    assert execution["task_id"] == task["id"]
    assert execution["provider"] == "mock"
    assert execution["total_tokens"] == 15
    assert execution["completed_at"] is not None
    assert execution["output_data"]["summary"] is not None

    # 6. Retrieve it by id independently.
    fetched = api_client.get(f"/api/v1/executions/{execution['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == execution["id"]

    # 7. Executions are listed under the task.
    listed = api_client.get(f"/api/v1/tasks/{task['id']}/executions")
    assert listed.status_code == 200
    assert [e["id"] for e in listed.json()] == [execution["id"]]

    # 8. The task is now completed.
    task_after = api_client.get(f"/api/v1/tasks/{task['id']}").json()
    assert task_after["status"] == "completed"
    assert task_after["executed_at"] is not None
