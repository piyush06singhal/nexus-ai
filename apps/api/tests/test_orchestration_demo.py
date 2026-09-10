"""Deterministic Phase 5 demo — "AI Market Research Team" (spec §34).

Creates four specialised mock agents (researcher, analyst, fact-checker,
writer), runs a market-analysis orchestration, and asserts the full pipeline:
decomposition → capability selection → parallel research tasks → writer
synthesis → completed with source attribution and a populated timeline.
"""

from __future__ import annotations

import json


def _create_agent(api_client, name, role, output):
    reply = json.dumps({"summary": f"{name} output", "output": output})
    resp = api_client.post(
        "/api/v1/agents",
        json={
            "name": name,
            "role": role,
            "status": "active",
            "provider": "mock",
            "model_name": "mock-model",
            "model_params": {"reply": reply},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_team(api_client):
    agents = {
        "researcher": _create_agent(
            api_client,
            "team-researcher",
            "researcher",
            {"market_size": 1200, "competitors": ["A", "B", "C"]},
        ),
        "analyst": _create_agent(
            api_client,
            "team-analyst",
            "analyst",
            {"trends": ["AI adoption", "consolidation"]},
        ),
        "fact_checker": _create_agent(
            api_client,
            "team-fact-checker",
            "fact_checker",
            {"verified": True, "uncertainties": []},
        ),
        "writer": _create_agent(
            api_client,
            "team-writer",
            "writer",
            {"report": "Competitive analysis complete"},
        ),
    }
    return agents


def test_market_research_demo(api_client):
    _seed_team(api_client)

    create = api_client.post(
        "/api/v1/orchestrations",
        json={"objective": "Analyze the competitive market and write a report"},
    )
    assert create.status_code == 201, create.text
    orch = create.json()
    assert orch["status"] == "created"

    execute = api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute")
    assert execute.status_code == 200, execute.text
    result = execute.json()

    # Full lifecycle reached a terminal state.
    assert result["status"] == "completed", result.get("error")

    # Decomposed into 4 tasks with a dependency graph.
    graph = result["execution_graph"]
    assert set(graph["tasks"]) == {"research", "analysis", "fact_checking", "writing"}
    assert set(graph["dependencies"]["writing"]) == {
        "research",
        "analysis",
        "fact_checking",
    }

    # All 4 agents selected (one per task).
    assert len(result["selected_agents"]) == 4

    # Final result shape with source attribution + no conflicts.
    final = result["final_result"]
    assert final["status"] == "completed"
    assert len(final["findings"]) == 4
    assert len(final["sources"]) == 4
    assert final["conflicts"] == []
    assert final["summary"]

    # Metrics present.
    metrics = result["metrics"]
    assert metrics["tasks_total"] == 4
    assert metrics["tasks_completed"] == 4
    assert metrics["tasks_failed"] == 0

    # Task-level detail consumed from the nested endpoint.
    tasks = api_client.get(f"/api/v1/orchestrations/{orch['id']}/tasks").json()
    assert len(tasks) == 4
    writer = next(t for t in tasks if t["name"] == "writing")
    assert writer["status"] == "completed"
    assert writer["output_data"]["report"] == "Competitive analysis complete"

    # Messages were recorded on the bus.
    messages = api_client.get(f"/api/v1/orchestrations/{orch['id']}/messages").json()
    assert any(m["message_type"] == "task_result" for m in messages)

    # Results aggregated with attribution.
    results = api_client.get(f"/api/v1/orchestrations/{orch['id']}/results").json()
    assert len(results) == 4
    assert all(r["agent_id"] is not None for r in results)

    # Timeline populated in order.
    timeline = api_client.get(f"/api/v1/orchestrations/{orch['id']}/timeline").json()
    event_types = [e["event_type"] for e in timeline]
    assert "created" in event_types
    assert "completed" in event_types
    assert timeline[0]["event_type"] == "created"
    assert timeline[-1]["event_type"] == "completed"


def test_generic_objective_single_task_demo(api_client):
    # A single "general" agent can satisfy an arbitrary objective.
    _create_agent(api_client, "generalist", "general", {"result": "done"})
    create = api_client.post(
        "/api/v1/orchestrations",
        json={"objective": "Help me decide what to eat"},
    )
    orch = create.json()
    execute = api_client.post(f"/api/v1/orchestrations/{orch['id']}/execute")
    result = execute.json()
    assert result["status"] == "completed", result.get("error")
    assert result["metrics"]["tasks_total"] == 1
    assert len(result["execution_graph"]["tasks"]) == 1
