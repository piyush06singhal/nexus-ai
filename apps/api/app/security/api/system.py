"""System endpoints (Phase 11) — health probes, metrics, feature flags."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db  # noqa: B008
from app.schemas.security import (
    FeatureFlagPublic,
    FeatureFlagSetRequest,
    HealthOverview,
    MetricsSnapshot,
    SystemHealthProbe,
    SystemHealthRecordPublic,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/system", tags=["system"])


# ── Health ──────────────────────────────────────────────────────────────────


@router.get("/health/live", response_model=SystemHealthProbe, status_code=200)
async def health_live():
    return SystemHealthProbe(status="ok", service="nexus")


@router.get("/health/ready", response_model=SystemHealthProbe, status_code=200)
async def health_ready(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    # Readiness = DB reachable (a single cheap round-trip). Failures raise 5xx.
    db.execute(select(1))
    return SystemHealthProbe(status="ok", service="nexus", checks={"database": "ok"})


@router.get("/health/dependencies", response_model=SystemHealthProbe, status_code=200)
async def health_dependencies(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """Dependency probe — no secrets. Down dependencies become check failures."""
    registry: dict[str, str] = {}
    try:
        db.execute(select(1))
        registry["database"] = "ok"
    except Exception:
        registry["database"] = "down"
    from app.core.redis import get_redis_client  # noqa: E402

    try:
        client = get_redis_client()
        await client.ping()
        registry["redis"] = "ok"
        await client.aclose()
    except Exception:
        registry["redis"] = "down"
    return SystemHealthProbe(
        status="ok" if all(v == "ok" for v in registry.values()) else "degraded",
        service="nexus",
        checks=registry,
    )


@router.get("/health/overview", response_model=HealthOverview, status_code=200)
async def health_overview(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import (
        AuditEvent,
        Incident,
        ResourceLimit,
        ResourceUsage,
        SecurityAlert,
    )

    def count(model) -> int:
        return len(list(db.execute(select(model.id)).scalars().all()))

    return HealthOverview(
        incidents_open=count(Incident),
        alerts_open=count(SecurityAlert),
        audit_events=count(AuditEvent),
        resource_limits=count(ResourceLimit),
        resource_usage_entries=count(ResourceUsage),
    )


# ── Metrics ─────────────────────────────────────────────────────────────────


@router.get("/metrics", response_model=MetricsSnapshot, status_code=200)
async def metrics_snapshot(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.core.metrics import registry

    # registry.snapshot() exposes the raw counters/gauges; the public
    # MetricsSnapshot contract flattens them into labels/values/counters +
    # an ISO recorded_at (matching the web MetricsSnapshot type).
    snap = registry.snapshot()
    return MetricsSnapshot(
        labels={
            "service": "api",
            "process_started_at": str(snap.get("process_started_at", "")),
        },
        values={k: float(v) for k, v in snap.get("gauges", {}).items()},
        counters={k: int(v) for k, v in snap.get("counters", {}).items()},
        recorded_at=datetime.now(UTC),
    )


# ── Feature flags ───────────────────────────────────────────────────────────


@router.get("/feature-flags", response_model=list[FeatureFlagPublic], status_code=200)
async def list_feature_flags(
    company_id: str | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import FeatureFlag

    stmt = select(FeatureFlag)
    if company_id is not None:
        stmt = stmt.where(FeatureFlag.company_id == company_id)
    flags = list(db.execute(stmt).scalars().all())
    return [FeatureFlagPublic.model_validate(f) for f in flags]


@router.post("/feature-flags", response_model=FeatureFlagPublic, status_code=201)
async def set_feature_flag(
    payload: FeatureFlagSetRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.flags import FeatureFlagService

    flag = FeatureFlagService(db).set_override(
        name=payload.name,
        enabled=payload.enabled,
        company_id=payload.company_id,
        set_by=identity.id,
    )
    db.commit()
    if flag is None:
        return FeatureFlagPublic(
            name=payload.name, enabled=payload.enabled, company_id=payload.company_id
        )
    return FeatureFlagPublic.model_validate(flag)


@router.get("/health-records", response_model=list[SystemHealthRecordPublic], status_code=200)
async def list_health_records(
    limit: int = 100,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import SystemHealthRecord

    stmt = select(SystemHealthRecord).order_by(SystemHealthRecord.recorded_at.desc()).limit(limit)
    rows = list(db.execute(stmt).scalars().all())
    return [SystemHealthRecordPublic.model_validate(r) for r in rows]
