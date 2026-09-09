"""Integration tests for the agent/task/execution API surface.

Uses the ``api_client`` fixture (SQLite in-memory DB + dependency overrides),
so no live PostgreSQL or model provider is required.
"""


def test_create_and_get_agent(api_client):
    r = api_client.post("/api/v1/agents", json={"name": "analyst", "role": "analyst"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "analyst"
    assert body["status"] == "draft"

    fetched = api_client.get(f"/api/v1/agents/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_create_duplicate_agent_conflicts(api_client):
    api_client.post("/api/v1/agents", json={"name": "dup"})
    r = api_client.post("/api/v1/agents", json={"name": "dup"})
    assert r.status_code == 409


def test_list_agents_with_status_filter(api_client):
    api_client.post("/api/v1/agents", json={"name": "a1", "status": "active"})
    api_client.post("/api/v1/agents", json={"name": "a2", "status": "draft"})
    r = api_client.get("/api/v1/agents?status=active")
    assert r.status_code == 200
    names = [a["name"] for a in r.json()]
    assert names == ["a1"]


def test_update_agent(api_client):
    created = api_client.post("/api/v1/agents", json={"name": "u1"}).json()
    r = api_client.patch(
        f"/api/v1/agents/{created['id']}", json={"status": "active", "role": "coder"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    assert r.json()["role"] == "coder"


def test_delete_agent(api_client):
    created = api_client.post("/api/v1/agents", json={"name": "gone"}).json()
    r = api_client.delete(f"/api/v1/agents/{created['id']}")
    assert r.status_code == 204
    assert api_client.get(f"/api/v1/agents/{created['id']}").status_code == 404


def test_get_missing_agent_returns_404(api_client):
    import uuid

    r = api_client.get(f"/api/v1/agents/{uuid.uuid4()}")
    assert r.status_code == 404


def test_create_and_get_task(api_client):
    r = api_client.post("/api/v1/tasks", json={"title": "Build X", "input_data": {"k": "v"}})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["input_data"] == {"k": "v"}

    fetched = api_client.get(f"/api/v1/tasks/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Build X"


def test_assign_task(api_client):
    agent = api_client.post("/api/v1/agents", json={"name": "worker"}).json()
    task = api_client.post("/api/v1/tasks", json={"title": "Assign me"}).json()
    r = api_client.post(f"/api/v1/tasks/{task['id']}/assign", json={"agent_id": agent["id"]})
    assert r.status_code == 200
    assert r.json()["assigned_agent_id"] == agent["id"]
    assert r.json()["status"] == "queued"
