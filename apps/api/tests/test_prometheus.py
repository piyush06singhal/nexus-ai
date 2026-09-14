"""Tests for Prometheus text exposition endpoint and prometheus_text() formatter."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.metrics import _MetricSet, prometheus_text

# ── prometheus_text() unit tests ────────────────────────────────────────────


def test_counter_total_suffix():
    r = _MetricSet()
    r.increment("request.api.test.total", 5)
    out = prometheus_text(r)
    assert "# TYPE request_api_test_total_total counter" in out
    assert "request_api_test_total_total 5" in out


def test_dot_to_underscore_normalization():
    r = _MetricSet()
    r.set_gauge("queue.depth", 42)
    out = prometheus_text(r)
    assert "# TYPE queue_depth gauge" in out
    assert "queue_depth 42" in out


def test_histogram_milliseconds_format():
    r = _MetricSet()
    r.add_histogram("request.latency_ms", 12.5)
    r.add_histogram("request.latency_ms", 37.0)
    out = prometheus_text(r)
    assert "# TYPE request_latency_ms_milliseconds histogram" in out
    assert "request_latency_ms_milliseconds_count 2" in out
    assert "request_latency_ms_milliseconds_sum 49.5" in out


def test_process_started_at_always_present():
    out = prometheus_text(_MetricSet())
    assert "nexus_process_started_at" in out


def test_empty_registry_produces_only_started_at():
    out = prometheus_text(_MetricSet())
    lines = [ln for ln in out.strip().splitlines() if not ln.startswith("#")]
    assert len(lines) == 1
    assert lines[0].startswith("nexus_process_started_at ")


# ── Endpoint integration test ──────────────────────────────────────────────


def test_prometheus_endpoint_returns_200(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", False)
    with TestClient(app=__import__("app.main", fromlist=["app"]).app) as client:
        resp = client.get("/api/v1/system/metrics/prometheus")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "# TYPE " in body
    assert "nexus_process_started_at" in body


def test_prometheus_endpoint_not_authenticated():
    """The /metrics/prometheus path must be accessible without auth."""
    import app.main as main_mod

    # Call with auth_enabled=True but no token — should still return 200
    with TestClient(app=main_mod.app) as client:
        resp = client.get("/api/v1/system/metrics/prometheus")
    # Endpoint is exempted from auth middleware, so it should not be 401/403
    assert resp.status_code == 200


def test_metrics_in_prometheus_format():
    """Smoke-test that live-metric paths produce valid Prometheus lines."""
    import app.main as main_mod

    with TestClient(app=main_mod.app) as client:
        resp = client.get("/api/v1/system/metrics/prometheus")
    lines = resp.text.strip().splitlines()
    for line in lines:
        if line.startswith("#"):
            continue
        # Every value line must be "metric_name number"
        parts = line.split()
        assert len(parts) == 2, f"bad line: {line}"
        _, val = parts
        float(val)  # must parse as number
