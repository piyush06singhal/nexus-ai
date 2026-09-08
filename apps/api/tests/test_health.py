"""Tests for the health endpoint."""


def test_health_returns_200_with_structure(healthy_client):
    response = healthy_client.get("/api/v1/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"]
    assert body["version"]
    assert body["environment"]
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"


def test_health_degrades_but_returns_200(degraded_client):
    response = degraded_client.get("/api/v1/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"]["status"] == "degraded"
    assert body["checks"]["redis"]["status"] == "degraded"


def test_root_endpoint(healthy_client):
    response = healthy_client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "service" in body
    assert "health" in body
