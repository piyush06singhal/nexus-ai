"""AI Employee OS — performance tracking and reviews.

Tracks metrics (tasks completed/failed, verification pass rate, average quality,
recovery rate, latency, cost, utilization, deadline adherence) and generates
reviews with strengths, weaknesses, skill changes, and recommendations.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.employee import AIEmployee, EmployeeReview
from app.employee.types import PerformanceMetrics


class PerformanceTracker:
    """Tracks and aggregates performance metrics for employees."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_metrics(
        self,
        employee_id: UUID,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> PerformanceMetrics:
        """Aggregate performance metrics for an employee."""
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return PerformanceMetrics(employee_id=employee_id)

        # Parse existing profile
        profile: dict[str, Any] = {}
        if emp.performance_profile:
            profile = json.loads(emp.performance_profile)

        return PerformanceMetrics(
            employee_id=employee_id,
            tasks_completed=profile.get("tasks_completed", 0),
            tasks_failed=profile.get("tasks_failed", 0),
            success_rate=profile.get("success_rate", 0.0),
            verification_pass_rate=profile.get("verification_pass_rate", 0.0),
            average_quality=profile.get("average_quality", 0.0),
            recovery_rate=profile.get("recovery_rate", 0.0),
            average_latency_ms=profile.get("average_latency_ms", 0.0),
            total_cost=profile.get("total_cost", 0.0),
            total_tokens=profile.get("total_tokens", 0),
            utilization=profile.get("utilization", 0.0),
            deadline_adherence=profile.get("deadline_adherence", 0.0),
            period_start=period_start,
            period_end=period_end,
        )

    def record_task_completion(
        self,
        employee_id: UUID,
        *,
        success: bool,
        quality: float = 0.5,
        latency_ms: float = 0.0,
        cost: float = 0.0,
        tokens: int = 0,
        verified: bool = False,
        recovered: bool = False,
        deadline_met: bool = True,
    ) -> None:
        """Record a single task completion event into the employee's profile."""
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return

        profile: dict[str, Any] = {}
        if emp.performance_profile:
            profile = json.loads(emp.performance_profile)

        # Increment counters
        if success:
            profile["tasks_completed"] = profile.get("tasks_completed", 0) + 1
        else:
            profile["tasks_failed"] = profile.get("tasks_failed", 0) + 1

        total = profile.get("tasks_completed", 0) + profile.get("tasks_failed", 0)
        profile["success_rate"] = profile.get("tasks_completed", 0) / total if total > 0 else 0.0

        # Running averages
        n = profile.get("_n", 0) + 1
        profile["_n"] = n

        prev_quality = profile.get("average_quality", 0.0)
        profile["average_quality"] = prev_quality + (quality - prev_quality) / n

        prev_latency = profile.get("average_latency_ms", 0.0)
        profile["average_latency_ms"] = prev_latency + (latency_ms - prev_latency) / n

        profile["total_cost"] = profile.get("total_cost", 0.0) + cost
        profile["total_tokens"] = profile.get("total_tokens", 0) + tokens

        if verified:
            prev_vr = profile.get("verification_pass_rate", 0.0)
            profile["verification_pass_rate"] = prev_vr + (1.0 - prev_vr) / n
        if recovered:
            prev_rr = profile.get("recovery_rate", 0.0)
            profile["recovery_rate"] = prev_rr + (1.0 - prev_rr) / n

        # Deadline adherence
        prev_da = profile.get("deadline_adherence", 0.0)
        da_val = 1.0 if deadline_met else 0.0
        profile["deadline_adherence"] = prev_da + (da_val - prev_da) / n

        emp.performance_profile = json.dumps(profile)
        self._db.flush()


class PerformanceReviewer:
    """Generates performance reviews from metrics."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._tracker = PerformanceTracker(db)

    def generate_review(
        self,
        employee_id: UUID,
        *,
        period_start: datetime,
        period_end: datetime | None = None,
    ) -> EmployeeReview:
        """Generate a performance review for the given period."""
        metrics = self._tracker.get_metrics(
            employee_id, period_start=period_start, period_end=period_end
        )

        strengths: list[str] = []
        weaknesses: list[str] = []
        recommendations: list[str] = []

        if metrics.success_rate >= 0.9:
            strengths.append("High task success rate")
        elif metrics.success_rate < 0.5:
            weaknesses.append("Low task success rate")
            recommendations.append("Review task assignment criteria")

        if metrics.verification_pass_rate >= 0.9:
            strengths.append("Strong verification pass rate")
        elif metrics.verification_pass_rate < 0.6:
            weaknesses.append("Below-target verification pass rate")
            recommendations.append("Increase verification scrutiny")

        if metrics.deadline_adherence >= 0.9:
            strengths.append("Excellent deadline adherence")
        elif metrics.deadline_adherence < 0.7:
            weaknesses.append("Missed deadlines")
            recommendations.append("Review workload capacity")

        if not strengths:
            strengths.append("Consistent performance")
        if not recommendations:
            recommendations.append("Continue current performance")

        review = EmployeeReview(
            employee_id=employee_id,
            period_start=period_start,
            period_end=period_end,
            metrics=json.dumps(
                {
                    "tasks_completed": metrics.tasks_completed,
                    "tasks_failed": metrics.tasks_failed,
                    "success_rate": metrics.success_rate,
                    "verification_pass_rate": metrics.verification_pass_rate,
                    "average_quality": metrics.average_quality,
                    "total_cost": metrics.total_cost,
                    "deadline_adherence": metrics.deadline_adherence,
                }
            ),
            strengths=json.dumps(strengths),
            weaknesses=json.dumps(weaknesses),
            recommendations=json.dumps(recommendations),
            reviewer="system",
        )
        self._db.add(review)
        self._db.flush()
        return review

    def get_reviews(self, employee_id: UUID, *, limit: int = 10) -> list[EmployeeReview]:
        """Fetch recent reviews for an employee."""
        stmt = (
            select(EmployeeReview)
            .where(EmployeeReview.employee_id == employee_id)
            .order_by(EmployeeReview.created_at.desc())
            .limit(limit)
        )
        return list(self._db.execute(stmt).scalars().all())
