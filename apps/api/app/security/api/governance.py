"""Governance endpoints (Phase 11) — flags/kill switch, policies, resources, approvals."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db  # noqa: B008
from app.schemas.security import (
    BreakGlassPublic,
    BreakGlassRequest,
    FlagSetRequest,
    GovernanceControlPublic,
    PolicyDecisionPublic,
    PolicyRuleCreate,
    PolicyRulePublic,
    ResourceLimitPublic,
    ResourceLimitSetRequest,
    ResourceUsagePublic,
    SystemFlagPublic,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/governance", tags=["governance"])


# ── System flags / kill switch ──────────────────────────────────────────────


@router.get("/flags", response_model=list[SystemFlagPublic], status_code=200)
async def list_flags(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import SystemFlag

    flags = list(db.execute(select(SystemFlag)).scalars().all())
    return [SystemFlagPublic.model_validate(f) for f in flags]


@router.post("/flags/{scope}/pause", response_model=SystemFlagPublic, status_code=200)
async def pause_scope(
    scope: str,
    payload: FlagSetRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.governance import KillSwitchService

    flag = KillSwitchService(db).pause(
        scope=scope,
        reason=payload.reason,
        set_by=identity.id,
        tenant_id=payload.tenant_id,
    )
    db.commit()
    return SystemFlagPublic.model_validate(flag)


@router.post("/flags/{scope}/resume", response_model=SystemFlagPublic, status_code=200)
async def resume_scope(
    scope: str,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.governance import KillSwitchService

    flag = KillSwitchService(db).resume(scope, by=identity.id)
    db.commit()
    return SystemFlagPublic.model_validate(flag)


# ── Policy rules ────────────────────────────────────────────────────────────


@router.get("/policies", response_model=list[PolicyRulePublic], status_code=200)
async def list_policies(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import PolicyRule

    stmt = select(PolicyRule)
    if company_id is not None:
        stmt = stmt.where(PolicyRule.company_id == company_id)
    rules = list(db.execute(stmt).scalars().all())
    return [PolicyRulePublic.model_validate(r) for r in rules]


@router.post("/policies", response_model=PolicyRulePublic, status_code=201)
async def create_policy(
    payload: PolicyRuleCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.policy import PolicyEngine

    rule = PolicyEngine(db).create_rule(
        effect=payload.effect,
        action_pattern=payload.action_pattern,
        scope=payload.scope,
        company_id=payload.company_id,
        resource_type=payload.resource_type,
        conditions=payload.conditions,
        reason=payload.reason,
        created_by=identity.id,
    )
    db.commit()
    return PolicyRulePublic.model_validate(rule)


@router.get("/policy-decisions", response_model=list[PolicyDecisionPublic], status_code=200)
async def list_policy_decisions(
    limit: int = 100,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import PolicyDecision

    stmt = select(PolicyDecision).order_by(PolicyDecision.created_at.desc()).limit(limit)
    rows = list(db.execute(stmt).scalars().all())
    return [PolicyDecisionPublic.model_validate(r) for r in rows]


# ── Resource limits / usage ─────────────────────────────────────────────────


@router.get("/limits", response_model=list[ResourceLimitPublic], status_code=200)
async def list_limits(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import ResourceLimit

    limits = list(db.execute(select(ResourceLimit)).scalars().all())
    return [ResourceLimitPublic.model_validate(lim) for lim in limits]


@router.post("/limits", response_model=ResourceLimitPublic, status_code=201)
async def set_limit(
    payload: ResourceLimitSetRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.resources import ResourceGovernanceService

    limit = ResourceGovernanceService(db).set_limit(
        category=payload.category,
        limit_value=payload.max_value,
        scope=payload.scope,
        company_id=payload.tenant_id,
        period=payload.period,
        set_by=identity.id,
    )
    db.commit()
    return ResourceLimitPublic.model_validate(limit)


@router.get("/resources/usage", response_model=list[ResourceUsagePublic], status_code=200)
async def list_usage(
    limit: int = 100,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import ResourceUsage

    stmt = select(ResourceUsage).order_by(ResourceUsage.recorded_at.desc()).limit(limit)
    rows = list(db.execute(stmt).scalars().all())
    return [ResourceUsagePublic.model_validate(r) for r in rows]


# ── Governance controls / break-glass ───────────────────────────────────────


@router.get("/controls", response_model=list[GovernanceControlPublic], status_code=200)
async def list_controls(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import GovernanceControl

    rows = list(db.execute(select(GovernanceControl)).scalars().all())
    return [GovernanceControlPublic.model_validate(r) for r in rows]


@router.post("/break-glass", response_model=BreakGlassPublic, status_code=201)
async def activate_break_glass(
    payload: BreakGlassRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.approvals import BreakGlassService

    bg = BreakGlassService(db).activate(
        scope=payload.scope,
        reason=payload.reason,
        requested_by=identity.id,
        company_id=payload.company_id,
        duration_minutes=payload.duration_minutes,
        permissions=payload.permissions,
    )
    db.commit()
    return BreakGlassPublic.model_validate(bg)


@router.get("/break-glass", response_model=list[BreakGlassPublic], status_code=200)
async def list_break_glass(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import BreakGlassAccess

    rows = (
        db.execute(select(BreakGlassAccess).order_by(BreakGlassAccess.requested_at.desc()))
        .scalars()
        .all()
    )
    return [BreakGlassPublic.model_validate(r) for r in rows]
