"""Request observability & API-security middleware (Phase 11, §45/§31).

Composed of small, independent ``BaseHTTPMiddleware`` pieces, each gated by its
own setting so the existing (auth-off) test surface is untouched and each piece
can be enabled independently in production:

- :class:`RequestContextMiddleware` — correlation ids. Reads/propagates
  ``X-Request-Id``/``X-Trace-Id``, binds them into ``request.state`` (+ the
  telemetry contextvars) so logs, audit and metrics for one request link up.
- :class:`SecurityHeadersMiddleware` — applies the configured response security
  headers without overriding anything a handler already set.
- :class:`RequestBodyLimitMiddleware` — rejects requests whose body exceeds
  ``settings.max_request_body_bytes`` with a 413-style error envelope.
- :class:`MetricsMiddleware` — records request count / latency / error metrics
  into the dependency-free registry behind ``/api/v1/system/metrics``.
- :class:`RateLimitMiddleware` — sliding-window in-memory limiter keyed by
  (client ip, route class). Stricter tiers apply to ``/auth/*`` (lockout
  protection) and expensive endpoints; ``rate_limit_enabled`` gate (off in
  dev/test, on in production).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.errors import NexusError, _error_envelope


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Generate / propagate correlation ids and bind them for the request."""

    async def dispatch(self, request: Request, call_next):
        from app.core import telemetry

        rid = request.headers.get("X-Request-Id") or telemetry.new_id()
        tid = request.headers.get("X-Trace-Id") or rid
        telemetry.set_correlation(request_id=rid, trace_id=tid)
        request.state.request_id = rid
        request.state.trace_id = tid
        try:
            response = await call_next(request)
        finally:
            telemetry.clear()
        response.headers.setdefault("X-Request-Id", rid)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Append configured response security headers (never override existing)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for name, value in settings.security_headers.items():
            response.headers.setdefault(name, value)
        return response


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """Reject request bodies above ``max_request_body_bytes`` (413 envelope)."""

    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            content_length = request.headers.get("Content-Length")
            try:
                too_large = (
                    content_length is not None
                    and int(content_length) > settings.max_request_body_bytes
                )
            except ValueError:
                too_large = False
            if too_large:
                return JSONResponse(
                    status_code=413,
                    content=_error_envelope(
                        NexusError(
                            "Request body exceeds the configured size limit.",
                            code="payload_too_large",
                        )
                    ),
                )
        return await call_next(request)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Request counters / latency / error into the dependency-free registry."""

    async def dispatch(self, request: Request, call_next):
        if not settings.metrics_enabled:
            return await call_next(request)
        from app.core import metrics

        handler = _route_name(request)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            metrics.request_metrics(
                handler,
                status_code=response.status_code,
                error=response.status_code >= 500,
            )
            return response
        except Exception:
            metrics.request_metrics(handler, error=True)
            raise
        finally:
            metrics.registry.observe_latency(
                f"request.{handler}.latency", time.perf_counter() - start
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter (per ip + route class).

    Inert unless ``rate_limit_enabled``. Default backend is in-memory deque
    timestamps per key capped at the class limit; with
    ``rate_limit_backend = "redis"`` the window moves to a shared Redis ZSET
    (see :mod:`app.core.ratelimit`). Excess requests return a 429 envelope.
    """

    def __init__(self, app):
        super().__init__(app)
        self._traffic: dict[tuple[str, str], deque] = defaultdict(deque)
        # Tier A: a Redis-backed (cross-process) backend is opt-in. The
        # injectable seam is only exercised when RATE_LIMIT_BACKEND=redis.
        self._limiter = None
        if settings.rate_limit_backend == "redis":
            from app.core.ratelimit import RedisRateLimiter

            self._limiter = RedisRateLimiter()

    @staticmethod
    def _rate_limited() -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content=_error_envelope(
                NexusError(
                    "Rate limit exceeded. Try again shortly.",
                    code="rate_limited",
                )
            ),
        )

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)
        ip = self._client_ip(request)
        route_class = self._class(request)

        if self._limiter is not None:
            # Redis-backed window (degrades to memory on Redis outage).
            if not await self._limiter.allow(ip, route_class, self._class_limit(request)):
                return self._rate_limited()
            return await call_next(request)

        key = (ip, route_class)
        bucket = self._traffic[key]
        now = time.monotonic()
        window = 60.0
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= self._class_limit(request):
            return self._rate_limited()
        bucket.append(now)
        return await call_next(request)

    @staticmethod
    def _client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    @classmethod
    def _class(cls, request: Request) -> str:
        path = request.url.path
        prefix = settings.api_v1_prefix
        if path.startswith(f"{prefix}/auth/"):
            return "auth"  # login/refresh → tighter lockout protection
        if path.startswith(f"{prefix}/external"):
            return "external"
        if any(
            path.startswith(f"{prefix}/{seg}/")
            for seg in ("orchestrations", "evaluations", "data", "system")
        ):
            return "expensive"
        return "default"

    def _class_limit(self, request: Request) -> int:
        return {
            "auth": settings.rate_limit_auth_per_minute,
            "external": settings.rate_limit_external_per_minute,
            "expensive": settings.rate_limit_expensive_per_minute,
            "default": settings.rate_limit_default_per_minute,
        }[self._class(request)]


def _route_name(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path.replace("/", ".").lstrip(".")
    return request.url.path.replace("/", ".").lstrip(".")


def install_security_middleware(app) -> None:
    """Attach the full Phase 11 middleware chain (idempotent, no auth changes).

    Order matters (outermost = first here from FastAPI's bottom-up add): the
    outermost effective order is request-context → security-headers → body
    limit → metrics → rate-limit → route handlers. Auth middleware is added in
    ``main.py`` after this so the bearer gate encloses everything else.
    """
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RateLimitMiddleware)
