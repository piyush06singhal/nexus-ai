"""Priority engine — explainable prioritization of work.

:class:`PriorityEngine` scores a target (project / objective / employee task /
decision) from configurable, weighted factors and records a
:class:`PriorityDecision` row so the reason behind every ranking is auditable.
Factors are observable inputs (mission alignment, strategic importance,
dependency impact, risk, resource cost, deadline urgency, blocking) — no opaque
scores.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.startup import PriorityDecision
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.types import PriorityFactor, PriorityResult

_DEFAULT_WEIGHTS: dict[PriorityFactor, float] = {
    PriorityFactor.MISSION_ALIGNMENT: 0.30,
    PriorityFactor.STRATEGIC_IMPORTANCE: 0.20,
    PriorityFactor.DEPENDENCY_IMPACT: 0.15,
    PriorityFactor.RISK: 0.10,
    PriorityFactor.RESOURCE_COST: 0.10,
    PriorityFactor.DEADLINE_URGENCY: 0.10,
    PriorityFactor.BLOCKING: 0.05,
}


class PriorityEngine:
    """Score and record explainable priorities for startup work."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    def score(
        self,
        *,
        company_id: UUID,
        target_type: str,
        target_id: UUID,
        factors: dict[PriorityFactor, float] | None = None,
        reason_hint: str | None = None,
        weights: dict[PriorityFactor, float] | None = None,
    ) -> PriorityResult:
        """Compute a weighted score and persist an auditable decision row."""
        weights = {**_DEFAULT_WEIGHTS, **(weights or {})}
        scores = {weights[factor]: float(value) for factor, value in (factors or {}).items()}
        score = sum(scores.values()) / sum(weights.values()) if weights and scores else 0.0
        reason = reason_hint or _default_reason(target_type, target_id)

        row = PriorityDecision(
            company_id=company_id,
            target_type=target_type,
            target_id=target_id,
            score=json.dumps(round(score, 4)),
            factors=json.dumps(
                {
                    getattr(factor, "value", factor): value
                    for factor, value in (factors or {}).items()
                },
                default=str,
            ),
            reason=reason,
        )
        self._db.add(row)
        self._db.commit()
        self._events.log(
            action=StartupEvents.PRIORITY_DECIDED,
            company_id=company_id,
            target_type=target_type,
            target_id=target_id,
            details={"score": round(score, 4), "reason": reason},
            outcome="success",
        )
        return PriorityResult(
            target_type=target_type,
            target_id=target_id,
            score=round(score, 4),
            factors={
                getattr(factor, "value", factor): value for factor, value in (factors or {}).items()
            },
            reason=reason,
        )

    def record(self, company_id: UUID, result: PriorityResult) -> PriorityResult:
        """Persist an already-computed PriorityResult (e.g. from a planner)."""
        row = PriorityDecision(
            company_id=company_id,
            target_type=result.target_type,
            target_id=result.target_id,
            score=json.dumps(result.score),
            factors=json.dumps(result.factors),
            reason=result.reason,
        )
        self._db.add(row)
        self._db.commit()
        return result

    def recent(self, company_id: UUID, *, limit: int = 25) -> list[dict[str, Any]]:
        stmt = (
            select(PriorityDecision)
            .where(PriorityDecision.company_id == company_id)
            .order_by(PriorityDecision.created_at.desc())
            .limit(limit)
        )
        return [_to_dict(r) for r in self._db.execute(stmt).scalars().all()]


def _to_dict(row: PriorityDecision) -> dict[str, Any]:
    def _loads(raw: str | None) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    return {
        "id": str(row.id),
        "company_id": str(row.company_id),
        "target_type": row.target_type,
        "target_id": str(row.target_id),
        "score": _loads(row.score),
        "factors": _loads(row.factors),
        "reason": row.reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _default_reason(target_type: str, target_id: UUID) -> str:
    return f"Priority scored for {target_type} {target_id}"
