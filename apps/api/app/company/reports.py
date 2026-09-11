"""AI Company Layer — organizational report generation.

Collects authoritative metrics, highlights, risks, blockers, goal progress, and
recommendations into a stored ``CompanyReport``. Recommendations are explicitly
non-executing — nothing is ever auto-run from a report (§28, §57). Every report
carries an ``evidence`` block linking it back to the source data, and a
``verification`` step that re-checks headline metrics against their authoritative
source before a report is marked ``verified`` (§58).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.alerts import CompanyHealth
from app.company.events import OrgEventLogger
from app.company.performance import PerformanceAggregator
from app.company.risks import RiskManager
from app.db.models.company import CompanyReport


class ReportGenerator:
    """Generate, verify, and retrieve organizational reports."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)

    def generate(
        self,
        company_id: UUID,
        *,
        report_type: str = "weekly",
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> CompanyReport:
        """Generate a report from authoritative data.

        Recommendations are guarding against any autonomous action.
        """
        now = datetime.now(UTC)
        period_start = period_start or (now - timedelta(days=7))
        period_end = period_end or now

        aggregator = PerformanceAggregator(self._db)
        agg = aggregator.aggregate(company_id)
        health = CompanyHealth(self._db).compute(company_id)
        risks = RiskManager(self._db).list_(company_id)
        risk_summary = [
            {
                "title": r.title,
                "severity": r.severity,
                "status": r.status.value,
                "probability": r.probability,
            }
            for r in risks
        ]
        goal_progress = self._goal_progress(company_id)

        metrics = {
            "task_volume": agg["task_volume"],
            "completed_tasks": agg["completed_tasks"],
            "success_rate": agg["success_rate"],
            "verification_rate": agg["verification_rate"],
            "recovery_rate": agg["recovery_rate"],
            "total_cost": agg["total_cost"],
            "average_latency_ms": agg["average_latency_ms"],
            "employee_utilization": agg["employee_utilization"],
            "goal_progress": agg["goal_progress"],
            "health_score": health["overall_score"],
        }
        highlights = self._highlights(agg, health)
        recommendations = self._recommendations(agg, health)
        blockers = [
            r["title"]
            for r in risk_summary
            if r["severity"] in ("critical", "high") and r["status"] in ("open", "mitigating")
        ]

        report = CompanyReport(
            company_id=company_id,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            metrics=json.dumps(metrics),
            highlights=json.dumps(highlights),
            risks=json.dumps(risk_summary),
            blockers=json.dumps(blockers[:10]),
            goal_progress=json.dumps(goal_progress),
            recommendations=json.dumps(recommendations),
            evidence=json.dumps(self._evidence(company_id, metrics)),
            verification_status="unverified",
        )
        self._db.add(report)
        self._db.flush()
        self.events.log(
            actor="system",
            action="report_generated",
            company_id=company_id,
            target_type="company_report",
            target_id=report.id,
            details={"report_type": report_type},
            outcome="success",
        )
        self._db.commit()
        return report

    def verify(self, report: CompanyReport) -> tuple[bool, str]:
        """Re-check headline metrics against authoritative sources."""
        try:
            metrics = json.loads(report.metrics) if report.metrics else {}
        except (json.JSONDecodeError, TypeError):
            metrics = {}
        aggregator = PerformanceAggregator(self._db)
        live = aggregator.aggregate(report.company_id)
        checks = []
        for key, live_val in (
            # compare stored vs live authoritative values (tolerating small drift)
            ("task_volume", live["task_volume"]),
            ("success_rate", live["success_rate"]),
            ("verification_rate", live["verification_rate"]),
            ("recovery_rate", live["recovery_rate"]),
        ):
            stored = metrics.get(key, 0)
            if abs(stored - live_val) > 0.01:
                checks.append(f"{key}: stored={stored:.2f} live={live_val:.2f}")
        verified = len(checks) == 0
        summary = (
            "All headline metrics match live authoritative data"
            if verified
            else "Mismatch detected: " + "; ".join(checks)
        )
        report.verification_status = "verified" if verified else "unverified"
        report.verification_summary = summary
        self._db.commit()
        return verified, summary

    def list_(self, company_id: UUID, *, report_type: str | None = None) -> list[CompanyReport]:
        stmt = (
            select(CompanyReport)
            .where(CompanyReport.company_id == company_id)
            .order_by(CompanyReport.created_at.desc())
        )
        if report_type is not None:
            stmt = stmt.where(CompanyReport.report_type == report_type)
        return list(self._db.execute(stmt).scalars().all())

    def get(self, report_id: UUID) -> CompanyReport | None:
        return self._db.get(CompanyReport, report_id)

    def to_dict(self, report: CompanyReport) -> dict[str, Any]:
        return {
            "id": str(report.id),
            "company_id": str(report.company_id),
            "report_type": report.report_type,
            "period_start": report.period_start.isoformat() if report.period_start else None,
            "period_end": report.period_end.isoformat() if report.period_end else None,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "metrics": json.loads(report.metrics) if report.metrics else None,
            "highlights": json.loads(report.highlights) if report.highlights else [],
            "risks": json.loads(report.risks) if report.risks else [],
            "blockers": json.loads(report.blockers) if report.blockers else [],
            "goal_progress": json.loads(report.goal_progress) if report.goal_progress else {},
            "recommendations": json.loads(report.recommendations) if report.recommendations else [],
            "evidence": json.loads(report.evidence) if report.evidence else {},
            "verification_status": report.verification_status,
            "verification_summary": report.verification_summary,
        }

    # ── Helpers ───────────────────────────────────────────────────────

    def _goal_progress(self, company_id: UUID) -> dict[str, Any]:
        from app.db.models.company import GoalScopeType, OrgGoal

        goals = list(
            self._db.execute(
                select(OrgGoal).where(
                    OrgGoal.company_id == company_id,
                    OrgGoal.scope_type == GoalScopeType.COMPANY,
                )
            ).scalars()
        )
        by_status: dict[str, int] = {}
        for g in goals:
            key = getattr(g.status, "value", str(g.status))
            by_status[key] = by_status.get(key, 0) + 1
        return {
            "total": len(goals),
            "average_progress": (
                round(sum(g.progress for g in goals) / len(goals) * 100, 2) if goals else 0.0
            ),
            "by_status": by_status,
        }

    def _highlights(self, agg: dict[str, Any], health: dict[str, Any]) -> list[str]:
        highlights = []
        if agg["success_rate"] >= 90:
            highlights.append(f"High task success rate ({agg['success_rate']:.0f}%)")
        if agg["verification_rate"] >= 85:
            highlights.append(f"Strong verification rate ({agg['verification_rate']:.0f}%)")
        if health["overall_score"] >= 80:
            highlights.append(f"Company health is strong ({health['overall_score']:.0f}/100)")
        if not highlights:
            highlights.append("Metrics are within acceptable ranges")
        return highlights

    def _recommendations(self, agg: dict[str, Any], health: dict[str, Any]) -> list[str]:
        """Non-executing recommendations — informational only."""
        recommendations = []
        if agg["verification_rate"] < 85:
            recommendations.append(
                f"Review failing verification paths ({agg['verification_rate']:.0f}% pass rate)"
            )
        if health["overall_score"] < 60:
            recommendations.append("Company health is degraded — review the weakest dimensions")
        if not recommendations:
            recommendations.append("No action items detected this period")
        return recommendations

    def _evidence(self, company_id: UUID, metrics: dict[str, Any]) -> dict[str, Any]:
        """Link the report back to its authoritative sources."""
        return {
            "company_id": str(company_id),
            "sources": [
                "tasks",
                "agent_executions",
                "verification_results",
                "recovery_attempts",
                "budgets",
                "goals",
                "risks",
            ],
            "generated_at": datetime.now(UTC).isoformat(),
            "metric_count": len(metrics),
        }
