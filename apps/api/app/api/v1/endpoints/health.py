"""Health endpoints.

Returns structured status for the API and its backing services. The
``/health`` endpoint always returns 200 when the API is reachable; individual
service checks degrade to ``"degraded"`` rather than failing the whole request,
so operators can distinguish "API down" from "backing dependency degraded".

Final-pass addition — canonical liveness/readiness/dependency probes (§14):

* ``/health/live`` — liveness probe: 200 as long as the process answers, with
  no dependency checks. Safe for load balancer / orchestrator health checks.
* ``/health/ready`` — readiness probe: 200 only when the API can actually serve
  (database reachable, Redis reachable); 503 otherwise. Safe for the container
  healthcheck so ``docker compose up`` only marks the API healthy once the
  schema is migrated and dependencies are up.
* ``/health/dependencies`` — detailed per-dependency report (database, redis,
  AI provider configuration, worker configuration). Never leaks values — key
  presence only.

These live under ``/api/v1/health/*`` which the Phase 11 auth whitelist exempts,
so they work in production with ``AUTH_ENABLED=true``. The Phase 11 system
probes (``/api/v1/system/health/*``) remain for authenticated operator use.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


class ServiceCheck(BaseModel):
    status: str  # "ok" | "degraded" | "unavailable"


class HealthResponse(BaseModel):
    status: str
    message: str
    service: str
    version: str
    environment: str
    checks: dict[str, ServiceCheck]


class HealthProbe(BaseModel):
    """Liveness/readiness probe body: status plus identifying metadata."""

    status: str
    service: str
    version: str
    environment: str
    checks: dict[str, ServiceCheck]


def _check_database(db: Session) -> ServiceCheck:
    try:
        db.execute(text("SELECT 1"))
        return ServiceCheck(status="ok")
    except Exception:
        return ServiceCheck(status="degraded")


def _check_redis() -> ServiceCheck:
    try:
        import redis

        # Probe the Redis server with a short timeout. In the Phase 0 runtime
        # Redis is optional, so a failed ping merely degrades the report.
        probe = redis.from_url(settings.redis_url, socket_connect_timeout=1)
        probe.ping()
        probe.close()
        return ServiceCheck(status="ok")
    except Exception:
        return ServiceCheck(status="degraded")


def _system_checks(db: Session) -> dict[str, ServiceCheck]:
    return {"database": _check_database(db), "redis": _check_redis()}


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health_check(db: Session = Depends(get_db)) -> HealthResponse:  # noqa: B008
    checks = _system_checks(db)
    all_ok = all(check.status == "ok" for check in checks.values())
    return HealthResponse(
        status="healthy" if all_ok else "degraded",
        message="NEXUS API is running."
        if all_ok
        else "NEXUS API is running with degraded dependencies.",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        checks=checks,
    )


@router.get(
    "/health/live",
    response_model=HealthProbe,
    summary="Liveness probe (process is up)",
)
async def health_live() -> HealthProbe:
    """Liveness: 200 whenever the process answers, no dependency checks."""
    return HealthProbe(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        checks={},
    )


@router.get(
    "/health/ready",
    response_model=HealthProbe,
    summary="Readiness probe (dependencies ready to serve)",
)
async def health_ready(db: Session = Depends(get_db)) -> HealthProbe:  # noqa: B008
    """Readiness: 200 only when the API can serve (DB + Redis reachable)."""
    checks = _system_checks(db)
    all_ok = all(check.status == "ok" for check in checks.values())
    if not all_ok:
        raise HTTPException(
            status_code=503,
            detail="not ready: one or more dependencies are unavailable",
        )
    return HealthProbe(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        checks=checks,
    )


@router.get(
    "/health/dependencies",
    response_model=HealthProbe,
    summary="Dependency probe (per-dependency status)",
)
async def health_dependencies(db: Session = Depends(get_db)) -> HealthProbe:  # noqa: B008
    """Per-dependency status — never leaks secret values (presence only)."""
    checks = _system_checks(db)

    # AI provider configuration: report configured vs default mock by key
    # PRESENCE only — never the key value.
    provider_keys = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")
    if any(os.environ.get(key) for key in provider_keys):
        checks["ai_provider"] = ServiceCheck(status="ok")
    else:
        checks["ai_provider"] = ServiceCheck(status="unavailable")

    checks["worker"] = ServiceCheck(
        status="ok" if settings.workflow_worker_enabled else "unavailable"
    )

    return HealthProbe(
        status="ok" if all(c.status == "ok" for c in checks.values()) else "degraded",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        checks=checks,
    )
