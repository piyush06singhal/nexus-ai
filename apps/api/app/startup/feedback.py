"""Feedback — structured signals from real operations, never auto-executed.

:class:`FeedbackService` converts observable signals (KPI attainment, task
success/failure, verification/recovery outcomes, project and product status,
risk and budget readings) into :class:`FeedbackRecord` rows backed by a
confidence score and a *recommendation*. Recommendations are advisory — the
replanning engine may act on them only within its bounded response set, and
neither the service nor any consumer executes recommendations directly.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.startup import MissionGraphRelation, StartupFeedback
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.graph import MissionGraphBuilder
from app.startup.types import FeedbackRecord


class FeedbackService:
    """Produce and record structured feedback from observable signals."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    def from_state(
        self,
        company_id: UUID,
        snapshot: Any,
        *,
        mission_id: UUID | None = None,
    ) -> list[FeedbackRecord]:
        """Derive feedback records from an observed company state snapshot."""
        records: list[FeedbackRecord] = []
        metrics = snapshot.metrics if hasattr(snapshot, "metrics") else {}

        success_rate = _metric(metrics, "completed_tasks", "failed_tasks")
        if success_rate is not None and success_rate < 0.7:
            records.append(
                FeedbackRecord(
                    category="execution_quality",
                    observation=f"Task success rate is {success_rate:.0%}, below the 70% bar",
                    source="state",
                    impact="Completed work quality is underperforming",
                    confidence=0.8,
                    recommendation="Prioritize verification and recovery on failing tasks",
                    objective_type={"kind": "execution"},
                )
            )

        kpis = metrics.get("kpis") or []
        missed = [k for k in kpis if isinstance(k, dict) and k.get("attainment", 1.0) < 0.7]
        if missed:
            names = ", ".join(str(k.get("name")) for k in missed[:4])
            records.append(
                FeedbackRecord(
                    category="kpi_underperformance",
                    observation=f"{len(missed)} KPI(s) below 70% of target: {names}",
                    source="state",
                    impact="Mission success criteria are at risk",
                    confidence=0.75,
                    recommendation="Replan around the underperforming KPIs",
                    objective_type={"kind": "kpi", "kpis": [k.get("name") for k in missed]},
                )
            )

        budget = metrics.get("budget") or {}
        utilization = float(budget.get("utilization", 0.0) or 0.0)
        if utilization > 0.9:
            records.append(
                FeedbackRecord(
                    category="budget_pressure",
                    observation=f"Budget utilization is {utilization:.0%} this cycle",
                    source="state",
                    impact="Remaining budget may be insufficient for the cycle",
                    confidence=0.9,
                    recommendation="Request a budget review or reduce scope",
                    objective_type={"kind": "budget"},
                )
            )

        open_risks = int(metrics.get("open_risks", 0) or 0)
        if open_risks >= 3:
            records.append(
                FeedbackRecord(
                    category="risk_exposure",
                    observation=f"{open_risks} open risks recorded",
                    source="state",
                    impact="Blocker or failure probability is elevated",
                    confidence=0.6,
                    recommendation="Reassess the riskiest project before more work",
                    objective_type={"kind": "risk"},
                )
            )

        for record in records:
            self.record(company_id, record, mission_id=mission_id)
        return records

    def record(
        self,
        company_id: UUID,
        record: FeedbackRecord,
        *,
        mission_id: UUID | None = None,
    ) -> StartupFeedback:
        row = StartupFeedback(
            company_id=company_id,
            mission_id=mission_id,
            objective_type=__import__("json").dumps(record.objective_type)
            if record.objective_type
            else None,
            source=record.source or "feedback_service",
            category=record.category,
            observation=record.observation,
            impact=record.impact,
            confidence=record.confidence,
            recommendation=record.recommendation,
            related_goal_id=record.related_goal_id,
            related_project_id=record.related_project_id,
            related_product_id=record.related_product_id,
        )
        self._db.add(row)
        self._db.commit()
        if mission_id is not None:
            MissionGraphBuilder(self._db).link(
                company_id=company_id,
                source_type="feedback",
                source_id=row.id,
                target_type="mission",
                target_id=mission_id,
                relation=MissionGraphRelation.GENERATED_BY,
                metadata={"category": record.category, "confidence": record.confidence},
                commit=False,
            )
            self._db.commit()
        self._events.log(
            action=StartupEvents.FEEDBACK_RECORDED,
            company_id=company_id,
            target_type="startup_feedback",
            target_id=row.id,
            details={
                "category": record.category,
                "confidence": record.confidence,
                "recommendation": record.recommendation,
            },
            outcome="success",
        )
        return row

    def list_(
        self,
        company_id: UUID,
        *,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        from sqlalchemy import select

        stmt = (
            select(StartupFeedback)
            .where(StartupFeedback.company_id == company_id)
            .order_by(StartupFeedback.created_at.desc())
            .limit(limit)
        )
        if category is not None:
            stmt = stmt.where(StartupFeedback.category == category)
        return [_feedback_to_dict(r) for r in self._db.execute(stmt).scalars().all()]


def _metric(metrics: dict, completed_key: str, failed_key: str) -> float | None:
    completed = int(metrics.get(completed_key, 0) or 0)
    failed = int(metrics.get(failed_key, 0) or 0)
    if completed + failed == 0:
        return None
    return completed / (completed + failed)


def _feedback_to_dict(row: StartupFeedback) -> dict[str, Any]:
    import json

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
        "mission_id": str(row.mission_id) if row.mission_id else None,
        "objective_type": _loads(row.objective_type),
        "source": row.source,
        "category": row.category,
        "observation": row.observation,
        "impact": row.impact,
        "confidence": row.confidence,
        "recommendation": row.recommendation,
        "related_goal_id": str(row.related_goal_id) if row.related_goal_id else None,
        "related_project_id": str(row.related_project_id) if row.related_project_id else None,
        "related_product_id": str(row.related_product_id) if row.related_product_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
