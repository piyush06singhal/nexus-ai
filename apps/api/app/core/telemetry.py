"""Correlation IDs & lightweight spans (Phase 11, §45).

Vendor-neutral tracing: every request carries a ``request_id``/``trace_id``
(propagated via the ``X-Request-Id`` / ``X-Trace-Id`` headers) and nested
spans are tracked as context-local counters. The web middleware attaches ids
to each incoming request; long-running workers (external action / workflow)
attach their own correlation id so their audit + log + metric records link up.
"""

from __future__ import annotations

import secrets
from contextlib import contextmanager
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_depth: ContextVar[int] = ContextVar("span_depth", default=0)


def new_id() -> str:
    return secrets.token_hex(8)


def current_request_id() -> str | None:
    return _request_id.get()


def current_trace_id() -> str | None:
    return _trace_id.get()


def set_correlation(*, request_id: str | None = None, trace_id: str | None = None) -> None:
    _request_id.set(request_id or new_id())
    _trace_id.set(trace_id or _request_id.get())


def bind(extra: dict) -> dict:
    """Attach correlation ids to a log ``extra`` mapping (caller-optimal)."""
    rid = current_request_id()
    tid = current_trace_id()
    if rid:
        extra["request_id"] = rid
    if tid and tid != rid:
        extra["trace_id"] = tid
    return extra


@contextmanager
def span(name: str):
    """Nested span context for block timing + logging."""
    depth = _span_depth.get()
    _span_depth.set(depth + 1)
    span_id = new_id()
    start = __import__("time").monotonic()
    try:
        yield span_id
    finally:
        elapsed = __import__("time").monotonic() - start
        _span_depth.set(depth)
        if elapsed > 0.0:
            from app.core.metrics import registry

            registry.observe_latency(f"span.{name}", elapsed)


def clear() -> None:
    _request_id.set(None)
    _trace_id.set(None)
    _span_depth.set(0)
