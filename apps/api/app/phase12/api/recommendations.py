"""Agent recommendation endpoints (Phase 12) — evidence-based, never fabricated.

Rankings use only real evaluation/benchmark data + measured signals; reasoning
and tradeoffs are exposed for each recommendation.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models.phase12 import AgentRecommendation
from app.db.session import get_db  # noqa: B008
from app.phase12.recommend import RecommendationEngine
from app.schemas.phase12 import AgentRecommendationPublic
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/agent-recommendations", tags=["recommendations"])


def _identity_id(identity) -> UUID | None:
    return getattr(identity, "id", None)


@router.get("", response_model=list[AgentRecommendationPublic], status_code=200)
async def list_recommendations(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rows = RecommendationEngine(db).list(company_id)
    return [AgentRecommendationPublic.model_validate(r) for r in rows]


@router.post("", response_model=list[AgentRecommendationPublic], status_code=201)
async def recommend(
    payload: dict,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    task_type = payload.get("task_type")
    if not task_type:
        raise HTTPException(status_code=400, detail="task_type is required")
    company_id = payload.get("company_id")
    require_approval = payload.get("require_approval", True)
    package_id = payload.get("package_id")
    rows = RecommendationEngine(db).recommend(
        company_id=UUID(str(company_id)) if company_id else None,
        task_type=task_type,
        skills=payload.get("skills"),
        budget_limit=payload.get("budget_limit"),
        latency_limit_ms=payload.get("latency_limit_ms"),
        require_approval=bool(require_approval),
        package_id=UUID(str(package_id)) if package_id else None,
        task_id=UUID(str(payload["task_id"])) if payload.get("task_id") else None,
    )
    return [AgentRecommendationPublic.model_validate(r) for r in rows]


@router.get("/{rec_id}", response_model=AgentRecommendationPublic, status_code=200)
async def get_recommendation(
    rec_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rec = db.get(AgentRecommendation, rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return AgentRecommendationPublic.model_validate(rec)


__all__ = ["router"]
