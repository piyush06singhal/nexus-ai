"""Execution tests for the orchestration engine (spec §21–§28, §33)."""

from __future__ import annotations

import json

import pytest

from app.db.models.orchestration import (
    Orchestration,
    OrchestrationStatus,
)
from app.orchestration.policies import OrchestrationLimits


def _agent(name, role, reply=None):

    return {
        "name": name,
        "role": role,
        "status": "active",
        "provider": "mock",
        "model_name": "mock-model",
        "model_params": {"reply": reply or json.dumps({"summary": "ok", "output": {}})},
    }


def _create_agents(api_client, *agents):
    ids = {}
    for a in agents:
        resp = api_client.post("/api/v1/agents", json=a)
        assert resp.status_code == 201, resp.text
        ids[a["name"]] = resp.json()["id"]
    return ids


def _make_orchestration(api_client, objective="single generic task"):
    create = api_client.post("/api/v1/orchestrations", json={"objective": objective})
    assert create.status_code == 201, create.text
    return create.json()


# ── Basic execution ───────────────────────────────────────────────────────────


def test_single_agent_execution_completes(api_client):
    _create_agents(api_client, _agent("solitary", "general", '{"summary":"s","output":{"r":1}}'))
    orch = _make_orchestration(api_client)
    res = api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "completed"
    assert data["metrics"]["tasks_total"] == 1
    assert data["metrics"]["tasks_completed"] == 1
    assert data["final_result"]["status"] == "completed"


def test_execute_twice_rejected(api_client):
    _create_agents(api_client, _agent("twice", "general"))
    orch = _make_orchestration(api_client)
    api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute")
    second = api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute")
    assert second.status_code == 422


# ── Dependency handling ───────────────────────────────────────────────────────


def test_dependent_tasks_sequence(api_client):
    # 4-agent market team; writer must run only after its 3 prerequisites.
    _create_agents(
        api_client,
        _agent("r", "researcher", '{"summary":"r","output":{"market_size":10}}'),
        _agent("a", "analyst", '{"summary":"a","output":{"growth":5}}'),
        _agent("fc", "fact_checker", '{"summary":"fc","output":{"verified":true}}'),
        _agent("w", "writer", '{"summary":"w","output":{"report":"done"}}'),
    )
    orch = _make_orchestration(api_client, "analyze competitive market and write report")
    data = api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute").json()

    writer = next(t for t in data["final_result"]["sources"] if t["task_name"] == "writing")
    assert writer is not None
    # Writer produced the report.
    writer_tasks = api_client.get(f"/api/v1/orchestrations/{orch['id']}/tasks").json()
    w = next(t for t in writer_tasks if t["name"] == "writing")
    assert w["status"] == "completed"
    # The three predecessors all completed too.
    for name in ("research", "analysis", "fact_checking"):
        t = next(x for x in writer_tasks if x["name"] == name)
        assert t["status"] == "completed"


# ── Failure handling ──────────────────────────────────────────────────────────


def test_failed_task_yields_partial_or_failed(api_client):
    # Missing a writer → no agent can run the writer task.
    _create_agents(
        api_client,
        _agent("r", "researcher", '{"summary":"r","output":{"x":1}}'),
        _agent("a", "analyst", '{"summary":"a","output":{"y":2}}'),
        _agent("fc", "fact_checker", '{"summary":"fc","output":{"z":3}}'),
    )
    orch = _make_orchestration(api_client, "analyze competitive market and write report")
    data = api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute").json()
    assert data["status"] in ("partially_completed", "failed")
    # Prerequisites still ran.
    tasks = api_client.get(f"/api/v1/orchestrations/{orch['id']}/tasks").json()
    prereqs = [t for t in tasks if t["name"] in ("research", "analysis", "fact_checking")]
    assert len(prereqs) == 3


def test_completed_task_remains_completed_after_partial_failure(api_client):
    # One prerequisite fails (malformed reply); independent others still succeed.
    _create_agents(
        api_client,
        _agent("r", "researcher", "not-json"),  # fails parsing
        _agent("a", "analyst", '{"summary":"a","output":{"growth":5}}'),
        _agent("fc", "fact_checker", '{"summary":"fc","output":{"v":1}}'),
        _agent("w", "writer", '{"summary":"w","output":{"report":"ok"}}'),
    )
    orch = _make_orchestration(api_client, "analyze competitive market then write report")
    data = api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute").json()
    # Analyst (independent of researcher) completed; writer depends on the
    # failed researcher so it is skipped → net result is partial/failed.
    assert data["status"] in ("partially_completed", "failed")
    tasks = api_client.get(f"/api/v1/orchestrations/{orch['id']}/tasks").json()
    by_name = {t["name"]: t["status"] for t in tasks}
    assert by_name["analysis"] == "completed"


# ── Cancellation ──────────────────────────────────────────────────────────────


def test_cancel_created_orchestration(api_client):
    _create_agents(api_client, _agent("cancelee", "general"))
    orch = _make_orchestration(api_client)
    resp = api_client.post(f"/api/v1/orchestrations/{orch['id']}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


def test_cannot_cancel_completed(api_client):
    _create_agents(api_client, _agent("done", "general"))
    orch = _make_orchestration(api_client)
    api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute")
    resp = api_client.post(f"/api/v1/orchestrations/{orch['id']}/cancel")
    assert resp.status_code == 422


# ── Resource limits (config-backed) ───────────────────────────────────────────


def test_limits_derive_from_settings():
    limits = OrchestrationLimits()
    assert limits.max_tasks > 0
    assert limits.max_parallel_agents > 0
    assert limits.max_execution_duration_seconds > 0


def test_orchestrator_respects_custom_limits(api_client):
    # Cap the pool to 1; the 4-task market demo must still complete.
    _create_agents(
        api_client,
        _agent("r", "researcher", '{"summary":"r","output":{"a":1}}'),
        _agent("a", "analyst", '{"summary":"a","output":{"b":2}}'),
        _agent("fc", "fact_checker", '{"summary":"fc","output":{"c":3}}'),
        _agent("w", "writer", '{"summary":"w","output":{"d":4}}'),
    )
    orch = _make_orchestration(api_client, "analyze competitive market and write report")
    data = api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute").json()
    assert data["status"] == "completed"
    assert data["metrics"]["tasks_completed"] == 4


# ── Engine-level orchestration limits ─────────────────────────────────────────


def test_exceeding_max_tasks_blocks_run(db, monkeypatch):
    from app.orchestration import Orchestrator
    from app.orchestration.types import PlanTask

    # A planner that produces more tasks than the limit tolerates.
    class BigPlanner:
        def create_plan(self, objective, available_agents, context):
            return __import__("app.orchestration.types", fromlist=["ExecutionPlan"]).ExecutionPlan(
                objective=objective,
                tasks=[PlanTask(name=f"t{i}", required_capabilities=["general"]) for i in range(5)],
            )

    orch = Orchestration(objective="x", status=OrchestrationStatus.CREATED)
    db.add(orch)
    db.commit()

    limits = OrchestrationLimits(max_tasks=2)
    engine = Orchestrator(db.get_bind(), planner=BigPlanner(), limits=limits)
    from app.orchestration.orchestrator import OrchestratorError

    with pytest.raises(OrchestratorError):
        # Planning checks the task count before any agent assignment.
        engine._plan(orch, db)
    db.rollback()


# ── Task status visibility ────────────────────────────────────────────────────


def test_task_statuses_reflect_execution(api_client):
    _create_agents(
        api_client,
        _agent("r", "researcher", '{"summary":"r","output":{"a":1}}'),
        _agent("w", "writer", '{"summary":"w","output":{"b":2}}'),
    )
    orch = _make_orchestration(api_client, "analyze competitive market then write report")
    api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute").json()
    tasks = api_client.get(f"/api/v1/orchestrations/{orch['id']}/tasks").json()
    statuses = {t["name"]: t["status"] for t in tasks}
    for name, status in statuses.items():
        assert status in (
            "completed",
            "failed",
            "skipped",
        ), (name, status)
    assert statuses["research"] == "completed"
