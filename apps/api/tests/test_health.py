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


# ── Final-pass probes (§14): /health/live, /health/ready, /health/dependencies


def test_health_live_returns_200_when_healthy(healthy_client):
    response = healthy_client.get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert body["version"]
    assert body["environment"]
    assert body["checks"] == {}


def test_health_live_stays_200_when_dependencies_down(degraded_client):
    """Liveness reflects only the process being up, never dependency state."""
    response = degraded_client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_ready_returns_200_when_dependencies_ok(healthy_client):
    response = healthy_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"


def test_health_ready_returns_503_when_dependency_down(degraded_client):
    response = degraded_client.get("/api/v1/health/ready")
    assert response.status_code == 503


def test_health_dependencies_reports_checks_without_secrets(healthy_client):
    response = healthy_client.get("/api/v1/health/dependencies")
    assert response.status_code == 200
    body = response.json()
    for name in ("database", "redis", "ai_provider", "worker"):
        assert name in body["checks"], f"missing dependency check {name}"
    # The document must never echo secret-bearing environment values.
    payload = str(body)
    assert "sk-" not in payload
    assert "api_key" not in payload.lower()
    import os

    for key, value in os.environ.items():
        if "key" in key.lower() or "secret" in key.lower() or "token" in key.lower():
            assert value not in payload, f"leaked env var {key}"


def test_health_dependencies_classes_worker_and_ai_provider_unconfigured(healthy_client):
    """With no provider keys and no worker, both are reported, not raised."""
    response = healthy_client.get("/api/v1/health/dependencies")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["ai_provider"]["status"] in ("ok", "unavailable")
    assert body["checks"]["worker"]["status"] in ("ok", "unavailable")
