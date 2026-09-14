"""Dependency-free metrics registry (Phase 11, §45 — vendor-neutral).

A tiny process-local registry of counters / gauges / histograms exposed via
``/api/v1/system/metrics``. Keyed by dotted names, e.g.
``request.total``, ``request.error``, ``request.latency_ms``,
``agent.steps``, ``tool.calls``, ``external.action``, ``verification.ok``,
``recovery.attempts``, ``queue.depth``, ``model.tokens``.

Thread-safe for the daemon-thread workers (worker/scheduler).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class _MetricSet:
    """Simple append-mostly metric store guarded by a lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._started = time.time()

    # ── writers ────────────────────────────────────────────────────────────

    def increment(self, name: str, amount: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += amount

    def count(self, name: str) -> float:
        with self._lock:
            return self._counters.get(name, 0.0)

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def add_histogram(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms[name].append(value)
            if len(self._histograms[name]) > 10_000:
                self._histograms[name] = self._histograms[name][-10_000:]

    def observe_latency(self, name: str, seconds: float) -> None:
        self.add_histogram(name, seconds * 1000.0)

    def timed(self, name: str):
        """Context manager that records elapsed seconds as ``name``.

        Usage::

            with registry.timed("request"):
                handle(request)
        """
        return _Timer(self, name)

    # ── snapshot ───────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            counters = {k: round(v, 4) for k, v in sorted(self._counters.items())}
            gauges = {k: round(v, 4) for k, v in sorted(self._gauges.items())}
            histos = {
                k: {"count": len(v), "sum_ms": round(sum(v), 4)}
                for k, v in sorted(self._histograms.items())
            }
        return {
            "process_started_at": round(self._started, 3),
            "counters": counters,
            "gauges": gauges,
            "histograms": histos,
        }


class _Timer:
    def __init__(self, registry: _MetricSet, name: str) -> None:
        self.registry = registry
        self.name = name
        self._start = 0.0

    def __enter__(self) -> _Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed = time.perf_counter() - self._start
        self.registry.observe_latency(self.name, elapsed)


registry = _MetricSet()


def request_metrics(handler_name: str, *, status_code: int | None = None, error: bool = False):
    registry.increment(f"request.{handler_name}.total")
    if error:
        registry.increment(f"request.{handler_name}.error")
    if status_code is not None:
        registry.increment(f"request.{handler_name}.status.{status_code}")


def workflow_metrics(queue_depth: int | None = None) -> None:
    registry.increment("queue.cycles")
    if queue_depth is not None:
        registry.set_gauge("queue.depth", float(queue_depth))


def model_tokens(model: str, input_tokens: int, output_tokens: int) -> None:
    registry.increment("model.tokens.input", float(input_tokens))
    registry.increment("model.tokens.output", float(output_tokens))
    registry.increment(f"model.{model}.calls")


# ── Prometheus text exposition ──────────────────────────────────────────────


def _prom_name(name: str) -> str:
    """Dots are illegal in Prometheus metric names — normalize to underscores."""
    return name.replace(".", "_")


def prometheus_text(local_registry: _MetricSet | None = None) -> str:
    """Render a snapshot in Prometheus text-exposition format (line protocol).

    Counters map to ``<name>_total``, gauges to ``<name>``, and histograms to
    ``<name>_milliseconds_count/_sum`` (bucket bounds are intentionally omitted —
    the registry stores only count+sum, which is enough for rate()/avg()). This
    is the wire format Prometheus scrapes; the JSON endpoint
    (``/api/v1/system/metrics``) remains for dashboards.
    """
    snap = (local_registry or registry).snapshot()
    lines: list[str] = []
    for name, value in snap["counters"].items():
        n = _prom_name(name)
        lines.append(f"# TYPE {n}_total counter")
        lines.append(f"{n}_total {value:g}")
    for name, value in snap["gauges"].items():
        n = _prom_name(name)
        lines.append(f"# TYPE {n} gauge")
        lines.append(f"{n} {value:g}")
    for name, hist in snap["histograms"].items():
        n = _prom_name(name)
        lines.append(f"# TYPE {n}_milliseconds histogram")
        lines.append(f"{n}_milliseconds_count {hist['count']}")
        lines.append(f"{n}_milliseconds_sum {hist['sum_ms']:g}")
    lines.append("# TYPE nexus_process_started_at gauge")
    lines.append(f"nexus_process_started_at {snap['process_started_at']:g}")
    return "\n".join(lines) + "\n"
