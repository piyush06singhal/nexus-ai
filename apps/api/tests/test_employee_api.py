"""API-level tests for AI Employee OS endpoints (Phase 7).

These test the HTTP layer — request/response, Pydantic validation,
status codes, and error handling — using the ``api_client`` fixture
(Real SQLite DB, FastAPI TestClient).
"""

from uuid import uuid4


def test_create_employee(api_client):
    resp = api_client.post(
        "/api/v1/employees",
        json={
            "name": "api-worker",
            "role": "analyst",
            "display_name": "API Worker",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "api-worker"
    assert data["role"] == "analyst"
    assert data["status"] == "draft"
    assert data["id"]


def test_list_employees(api_client):
    api_client.post("/api/v1/employees", json={"name": "list-a"})
    api_client.post("/api/v1/employees", json={"name": "list-b"})
    resp = api_client.get("/api/v1/employees")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    names = [e["name"] for e in data["items"]]
    assert "list-a" in names
    assert "list-b" in names


def test_list_employees_filter_by_status(api_client):
    r1 = api_client.post("/api/v1/employees", json={"name": "filter-draft"})
    emp_id = r1.json()["id"]
    api_client.post("/api/v1/employees", json={"name": "filter-active"})
    # Activate the second one
    api_client.post(f"/api/v1/employees/{emp_id}/activate")

    resp = api_client.get("/api/v1/employees?status=active")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(e["status"] == "active" for e in items)
    assert any(e["name"] == "filter-draft" for e in items)


def test_get_employee(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "get-me"})
    emp_id = r.json()["id"]
    resp = api_client.get(f"/api/v1/employees/{emp_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "get-me"


def test_get_employee_not_found(api_client):
    resp = api_client.get(f"/api/v1/employees/{uuid4()}")
    assert resp.status_code == 404


def test_update_employee(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "upd-worker"})
    emp_id = r.json()["id"]
    resp = api_client.put(
        f"/api/v1/employees/{emp_id}",
        json={
            "display_name": "Updated Worker",
            "department": "engineering",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Worker"
    assert resp.json()["department"] == "engineering"


def test_delete_employee(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "del-worker"})
    emp_id = r.json()["id"]
    resp = api_client.delete(f"/api/v1/employees/{emp_id}")
    assert resp.status_code == 204
    # Confirm gone
    resp = api_client.get(f"/api/v1/employees/{emp_id}")
    assert resp.status_code == 404


def test_delete_employee_not_found(api_client):
    resp = api_client.delete(f"/api/v1/employees/{uuid4()}")
    assert resp.status_code == 404


def test_lifecycle_activate(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "lifecycle-act"})
    emp_id = r.json()["id"]
    resp = api_client.post(f"/api/v1/employees/{emp_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["availability"] == "available"


def test_lifecycle_pause(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "lifecycle-pause"})
    emp_id = r.json()["id"]
    api_client.post(f"/api/v1/employees/{emp_id}/activate")
    resp = api_client.post(f"/api/v1/employees/{emp_id}/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


def test_lifecycle_resume(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "lifecycle-resume"})
    emp_id = r.json()["id"]
    api_client.post(f"/api/v1/employees/{emp_id}/activate")
    api_client.post(f"/api/v1/employees/{emp_id}/pause")
    resp = api_client.post(f"/api/v1/employees/{emp_id}/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_lifecycle_suspend(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "lifecycle-suspend"})
    emp_id = r.json()["id"]
    api_client.post(f"/api/v1/employees/{emp_id}/activate")
    resp = api_client.post(f"/api/v1/employees/{emp_id}/suspend")
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"


def test_lifecycle_terminate(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "lifecycle-term"})
    emp_id = r.json()["id"]
    api_client.post(f"/api/v1/employees/{emp_id}/activate")
    resp = api_client.post(f"/api/v1/employees/{emp_id}/terminate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "terminated"


def test_lifecycle_invalid_transition_returns_error(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "lifecycle-invalid"})
    emp_id = r.json()["id"]
    # DRAFT → TERMINATED is invalid
    resp = api_client.post(f"/api/v1/employees/{emp_id}/terminate")
    assert resp.status_code in (400, 422)


def test_lifecycle_not_found(api_client):
    resp = api_client.post(f"/api/v1/employees/{uuid4()}/activate")
    assert resp.status_code == 404


def test_assign_task_to_employee(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "assign-target"})
    emp_id = r.json()["id"]
    api_client.post(f"/api/v1/employees/{emp_id}/activate")
    resp = api_client.post(
        f"/api/v1/employees/{emp_id}/tasks",
        json={
            "task_title": "Do research",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["employee_id"] == emp_id
    assert data["task_id"] is not None  # assignment persists a real Task


def test_get_employee_tasks_inbox(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "inbox-api"})
    emp_id = r.json()["id"]
    api_client.post(f"/api/v1/employees/{emp_id}/activate")
    api_client.post(f"/api/v1/employees/{emp_id}/tasks", json={"task_title": "Inbox A"})
    api_client.post(f"/api/v1/employees/{emp_id}/tasks", json={"task_title": "Inbox B"})

    resp = api_client.get(f"/api/v1/employees/{emp_id}/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 2
    assert {t["title"] for t in tasks} == {"Inbox A", "Inbox B"}
    assert all(t["status"] == "queued" for t in tasks)


def test_workload_reflects_assigned_task(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "workload-real"})
    emp_id = r.json()["id"]
    api_client.post(f"/api/v1/employees/{emp_id}/activate")
    api_client.post(f"/api/v1/employees/{emp_id}/tasks", json={"task_title": "Count me"})

    resp = api_client.get(f"/api/v1/employees/{emp_id}/workload")
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued_tasks"] == 1  # was hardcoded 0 before the fix
    assert data["active_tasks"] == 0


def test_execute_employee_task(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "exec-api"})
    emp_id = r.json()["id"]
    api_client.post(f"/api/v1/employees/{emp_id}/activate")
    assign = api_client.post(f"/api/v1/employees/{emp_id}/tasks", json={"task_title": "Run me"})
    task_id = assign.json()["task_id"]

    resp = api_client.post(f"/api/v1/employees/{emp_id}/tasks/{task_id}/execute")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == task_id
    assert data["status"] in ("succeeded", "failed")


def test_execute_employee_task_non_member_task(api_client):
    """Executing a task that belongs to another employee should 404."""
    a = api_client.post("/api/v1/employees", json={"name": "exec-a"}).json()["id"]
    b = api_client.post("/api/v1/employees", json={"name": "exec-b"}).json()["id"]
    api_client.post(f"/api/v1/employees/{a}/activate")
    api_client.post(f"/api/v1/employees/{b}/activate")
    assign = api_client.post(f"/api/v1/employees/{a}/tasks", json={"task_title": "A's task"})
    task_id = assign.json()["task_id"]

    resp = api_client.post(f"/api/v1/employees/{b}/tasks/{task_id}/execute")
    assert resp.status_code == 404


def test_auto_assign(api_client):
    api_client.post("/api/v1/employees", json={"name": "auto-a"})
    api_client.post("/api/v1/employees", json={"name": "auto-b"})
    # Activate both
    list_resp = api_client.get("/api/v1/employees")
    for emp in list_resp.json()["items"]:
        api_client.post(f"/api/v1/employees/{emp['id']}/activate")

    resp = api_client.post(
        "/api/v1/employees/assign",
        json={
            "task_title": "Auto task",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["employee_id"]


def test_get_workload(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "workload-get"})
    emp_id = r.json()["id"]
    resp = api_client.get(f"/api/v1/employees/{emp_id}/workload")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_tasks" in data
    assert "capacity" in data
    assert "utilization" in data


def test_get_skills(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "skills-get"})
    emp_id = r.json()["id"]
    resp = api_client.get(f"/api/v1/employees/{emp_id}/skills")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_goals_crud_via_api(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "goals-api"})
    emp_id = r.json()["id"]
    # Create goal
    resp = api_client.post(
        f"/api/v1/employees/{emp_id}/goals",
        json={
            "title": "Improve speed",
            "priority": 1,
        },
    )
    assert resp.status_code == 201
    goal = resp.json()
    assert goal["title"] == "Improve speed"
    assert goal["status"] == "not_started"

    # List goals
    resp = api_client.get(f"/api/v1/employees/{emp_id}/goals")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_performance(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "perf-api"})
    emp_id = r.json()["id"]
    resp = api_client.get(f"/api/v1/employees/{emp_id}/performance")
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks_completed" in data
    assert "success_rate" in data
    assert "average_quality" in data


def test_get_timeline(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "timeline-api"})
    emp_id = r.json()["id"]
    resp = api_client.get(f"/api/v1/employees/{emp_id}/timeline")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 1  # At least the "created" event
    assert events[0]["event_type"] == "created"


def test_get_audit_log(api_client):
    r = api_client.post("/api/v1/employees", json={"name": "audit-api"})
    emp_id = r.json()["id"]
    resp = api_client.get(f"/api/v1/employees/{emp_id}/audit")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1
    assert entries[0]["action"] == "created"


def test_workforce_overview(api_client):
    api_client.post("/api/v1/employees", json={"name": "wf-a"})
    api_client.post("/api/v1/employees", json={"name": "wf-b"})
    resp = api_client.get("/api/v1/employees/workforce")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_employees"] >= 2
    assert "by_status" in data


def test_create_employee_with_skills_via_api(api_client):
    resp = api_client.post(
        "/api/v1/employees",
        json={
            "name": "skilled-api",
            "role": "developer",
            "skills": [{"skill_id": "s1", "name": "python", "proficiency": 0.8}],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["skills"] is not None
    assert len(data["skills"]) == 1
    assert data["skills"][0]["name"] == "python"


def test_create_employee_minimal(api_client):
    resp = api_client.post("/api/v1/employees", json={"name": "minimal-api"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "minimal-api"
    assert data["role"] == "general"
    assert data["status"] == "draft"
    assert data["memory_namespace"] == "employee:minimal-api"
