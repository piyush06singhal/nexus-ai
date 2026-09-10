"""Tests for the memory HTTP API (Phase 4)."""

from datetime import UTC
from uuid import uuid4

MEMORY_PAYLOAD = {
    "namespace": "default",
    "type": "semantic",
    "content": "Revenue grew 12% quarter over quarter",
    "importance": 0.7,
    "confidence": 0.9,
}


def test_create_and_get_memory(api_client):
    r = api_client.post("/api/v1/memories", json=MEMORY_PAYLOAD)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["content"] == MEMORY_PAYLOAD["content"]
    assert body["type"] == "semantic"
    assert body["status"] == "active"

    mid = body["id"]
    got = api_client.get(f"/api/v1/memories/{mid}")
    assert got.status_code == 200
    assert got.json()["id"] == mid


def test_list_memories_in_namespace(api_client):
    api_client.post("/api/v1/memories", json=MEMORY_PAYLOAD)
    r = api_client.get("/api/v1/memories", params={"namespace": "default"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert all(m["namespace"] == "default" for m in body["memories"])


def test_list_namespace_required(api_client):
    r = api_client.get("/api/v1/memories")
    assert r.status_code == 422  # namespace is required


def test_update_memory(api_client):
    created = api_client.post("/api/v1/memories", json=MEMORY_PAYLOAD).json()
    r = api_client.patch(
        f"/api/v1/memories/{created['id']}", json={"importance": 0.99, "content": "Updated"}
    )
    assert r.status_code == 200
    assert r.json()["importance"] == 0.99
    assert r.json()["content"] == "Updated"


def test_delete_memory(api_client):
    created = api_client.post("/api/v1/memories", json=MEMORY_PAYLOAD).json()
    r = api_client.delete(f"/api/v1/memories/{created['id']}")
    assert r.status_code == 204
    assert api_client.get(f"/api/v1/memories/{created['id']}").status_code == 404


def test_archive_memory(api_client):
    created = api_client.post("/api/v1/memories", json=MEMORY_PAYLOAD).json()
    r = api_client.post(f"/api/v1/memories/{created['id']}/archive")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_search_memories_keyword(api_client):
    api_client.post("/api/v1/memories", json=MEMORY_PAYLOAD)
    r = api_client.post(
        "/api/v1/memories/search",
        json={"query": "Revenue growth", "namespace": "default", "top_k": 5},
    )
    assert r.status_code == 200
    results = r.json()
    assert results, "search should return the seeded memory"
    assert "score" in results[0]
    assert "breakdown" in results[0]
    assert results[0]["memory"]["type"] == "semantic"


def test_search_respects_query_specificity(api_client):
    api_client.post(
        "/api/v1/memories",
        json={**MEMORY_PAYLOAD, "content": "pasta carbonara recipe"},
    )
    r = api_client.post(
        "/api/v1/memories/search",
        json={"query": "quantum physics zzz", "namespace": "default", "min_score": 0.9},
    )
    assert r.status_code == 200
    assert r.json() == []


def test_cleanup_expired(api_client):
    from datetime import datetime, timedelta

    payload = {
        "namespace": "default",
        "type": "working",
        "content": "stale",
        "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
    }
    api_client.post("/api/v1/memories", json=payload)
    r = api_client.post("/api/v1/memories/cleanup")
    assert r.status_code == 200
    assert r.json()["expired_count"] >= 1


def test_get_missing_returns_404(api_client):
    r = api_client.get(f"/api/v1/memories/{uuid4()}")
    assert r.status_code == 404


def test_create_validation_error(api_client):
    r = api_client.post("/api/v1/memories", json={"namespace": "default"})
    assert r.status_code == 422  # missing type + content
