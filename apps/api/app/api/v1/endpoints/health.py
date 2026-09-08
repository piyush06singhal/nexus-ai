"""Health check endpoint.

Returns structured status for the API and its backing services. The endpoint
always returns 200 when the API is reachable; individual service checks
degrade to ``"degraded"`` rather than failing the whole request, so operators
can distinguish "API down" from "backing dependency degraded".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
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


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health_check(db: Session = Depends(get_db)) -> HealthResponse:  # noqa: B008
    db_check = _check_database(db)
    redis_check = _check_redis()

    all_ok = db_check.status == "ok" and redis_check.status == "ok"
    return HealthResponse(
        status="healthy" if all_ok else "degraded",
        message="NEXUS API is running."
        if all_ok
        else "NEXUS API is running with degraded dependencies.",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        checks={"database": db_check, "redis": redis_check},
    )
