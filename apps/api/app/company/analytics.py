"""AI Company Layer — analytics and forecasting.

Provides workforce, operations, reliability, finance, and strategy analytics
(§55) aggregated from real operational data. :class:`ForecastService` produces
deterministic projections (budget burn rate, goal completion extrapolation)
using simple linear models — no autonomous strategy generation (§56).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.company.membership import MembershipManager
from app.db.models.company import (
    Budget,
    Department,
    GoalScopeType,
    OrgGoal,
    Risk,
    RiskStatus,
)
from app.db.models.employee import AIEmployee
from app.db.models.execution import AgentExecution
from app.db.models.reliability import VerificationResult
from app.db.models.task import Task, TaskStatus
from app.db.models.tool_call import ToolCallRecord


class AnalyticsService:
    """Aggregate analytics across workforce, operations, reliability, finance,
    and strategy dimensions.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def workforce_analytics(self, company_id: UUID) -> dict[str, Any]:
        """Headcount, department distribution, role distribution, manager span."""
        memberships = list(
            self._db.execute(
                select(Department).where(Department.company_id == company_id)
            ).scalars()
        )
        emp_count = len(MembershipManager(self._db).list_employees(company_id))
        dept_count = len(memberships)
        role_dist: dict[str, int] = {}
        from app.db.models.company import OrganizationalMembership, OrganizationalRole

        rows = self._db.execute(
            select(OrganizationalRole.name, func.count(OrganizationalMembership.id))
            .outerjoin(
                OrganizationalMembership,
                OrganizationalMembership.role_id == OrganizationalRole.id,
            )
            .where(OrganizationalRole.company_id == company_id)
            .group_by(OrganizationalRole.name)
        ).all()
        for role_name, count in rows:
            role_dist[role_name] = count

        return {
            "company_id": str(company_id),
            "total_employees": emp_count,
            "total_departments": dept_count,
            "role_distribution": role_dist,
        }

    def operations_analytics(self, company_id: UUID) -> dict[str, Any]:
        """Task throughput, status distribution, average latency, tool usage."""
        from app.db.models.company import OrganizationalMembership

        emp_ids = list(
            self._db.execute(
                select(OrganizationalMembership.employee_id).where(
                    OrganizationalMembership.company_id == company_id
                )
            ).scalars()
        )
        if not emp_ids:
            return self._empty_ops()
        agent_ids = [
            aid
            for aid in self._db.execute(
                select(AIEmployee.agent_id).where(
                    AIEmployee.id.in_(emp_ids), AIEmployee.agent_id.is_not(None)
                )
            ).scalars()
        ]
        if not agent_ids:
            return self._empty_ops()

        status_counts = dict(
            self._db.execute(
                select(Task.status, func.count(Task.id))
                .where(Task.assigned_agent_id.in_(agent_ids))
                .group_by(Task.status)
            ).all()
        )
        total_tasks = sum(status_counts.values())
        completed = sum(
            count
            for s, count in status_counts.items()
            if (getattr(s, "value", s) == TaskStatus.COMPLETED.value)
        )
        failed = sum(
            count
            for s, count in status_counts.items()
            if (getattr(s, "value", s) == TaskStatus.FAILED.value)
        )
        avg_latency = self._db.scalar(
            select(func.avg(AgentExecution.latency_ms)).where(
                AgentExecution.agent_id.in_(agent_ids)
            )
        )
        total_tool_calls = (
            self._db.scalar(
                select(func.count(ToolCallRecord.id)).where(
                    ToolCallRecord.execution_id.in_(
                        select(AgentExecution.id).where(AgentExecution.agent_id.in_(agent_ids))
                    )
                )
            )
            or 0
        )

        return {
            "company_id": str(company_id),
            "total_tasks": total_tasks,
            "completed": completed,
            "failed": failed,
            "success_rate": (
                round((completed / (completed + failed)) * 100, 2) if (completed + failed) else 0.0
            ),
            "average_latency_ms": round(float(avg_latency), 2) if avg_latency else 0.0,
            "total_tool_calls": int(total_tool_calls),
        }

    def _empty_ops(self) -> dict[str, Any]:
        return {
            "total_tasks": 0,
            "completed": 0,
            "failed": 0,
            "success_rate": 0.0,
            "average_latency_ms": 0.0,
            "total_tool_calls": 0,
        }

    def reliability_analytics(self, company_id: UUID) -> dict[str, Any]:
        """Verification pass/fail distribution, recovery rate."""
        from app.db.models.company import OrganizationalMembership
        from app.db.models.reliability import RecoveryAttempt

        emp_ids = list(
            self._db.execute(
                select(OrganizationalMembership.employee_id).where(
                    OrganizationalMembership.company_id == company_id
                )
            ).scalars()
        )
        if not emp_ids:
            return {"verification_rate": 0.0, "recovery_rate": 0.0}
        agent_ids = [
            aid
            for aid in self._db.execute(
                select(AIEmployee.agent_id).where(
                    AIEmployee.id.in_(emp_ids), AIEmployee.agent_id.is_not(None)
                )
            ).scalars()
        ]
        if not agent_ids:
            return {"verification_rate": 0.0, "recovery_rate": 0.0}

        v_total = (
            self._db.scalar(
                select(func.count(VerificationResult.id))
                .join(AgentExecution, AgentExecution.id == VerificationResult.execution_id)
                .where(AgentExecution.agent_id.in_(agent_ids))
            )
            or 0
        )
        v_pass = (
            self._db.scalar(
                select(func.count(VerificationResult.id))
                .join(AgentExecution, AgentExecution.id == VerificationResult.execution_id)
                .where(
                    AgentExecution.agent_id.in_(agent_ids),
                    VerificationResult.status == "pass",
                )
            )
            or 0
        )
        r_total = (
            self._db.scalar(
                select(func.count(RecoveryAttempt.id))
                .join(AgentExecution, AgentExecution.id == RecoveryAttempt.execution_id)
                .where(AgentExecution.agent_id.in_(agent_ids))
            )
            or 0
        )
        r_recovered = (
            self._db.scalar(
                select(func.count(RecoveryAttempt.id))
                .join(AgentExecution, AgentExecution.id == RecoveryAttempt.execution_id)
                .where(
                    AgentExecution.agent_id.in_(agent_ids),
                    RecoveryAttempt.outcome == "recovered",
                )
            )
            or 0
        )
        return {
            "verification_rate": round((v_pass / v_total) * 100, 2) if v_total else 0.0,
            "recovery_rate": round((r_recovered / r_total) * 100, 2) if r_total else 0.0,
            "verification_volume": v_total,
            "recovery_volume": r_total,
        }

    def finance_analytics(self, company_id: UUID) -> dict[str, Any]:
        """Total spend, budget utilization, cost per execution."""
        budget = self._db.execute(
            select(Budget).where(
                Budget.company_id == company_id,
                Budget.scope_type == GoalScopeType.COMPANY,
            )
        ).scalar_one_or_none()
        if budget is None:
            return {"total_spend": 0.0, "budget_utilization": 0.0, "cost_per_execution": 0.0}
        utilization = (budget.spent / budget.monthly_limit * 100) if budget.monthly_limit else 0.0
        cost_per_exec = (budget.spent / budget.execution_count) if budget.execution_count else 0.0
        return {
            "total_spend": round(budget.spent, 2),
            "budget_utilization": round(utilization, 2),
            "cost_per_execution": round(cost_per_exec, 4),
            "tokens_used": budget.tokens_used,
            "tool_calls_used": budget.tool_calls_used,
            "execution_count": budget.execution_count,
        }

    def strategy_analytics(self, company_id: UUID) -> dict[str, Any]:
        """Goal progress distribution, KPI trend summary, risk counts."""
        goals = list(
            self._db.execute(select(OrgGoal).where(OrgGoal.company_id == company_id)).scalars()
        )
        goal_progress = {
            "total": len(goals),
            "completed": sum(1 for g in goals if g.status == "completed"),
            "active": sum(1 for g in goals if g.status == "active"),
            "at_risk": sum(1 for g in goals if g.status == "at_risk"),
            "average_progress": (
                round(sum(g.progress for g in goals) / len(goals) * 100, 2) if goals else 0.0
            ),
        }
        risk_counts: dict[str, int] = {}
        for r in self._db.execute(
            select(Risk.severity, func.count(Risk.id))
            .where(Risk.company_id == company_id)
            .group_by(Risk.severity)
        ).all():
            risk_counts[str(r[0])] = r[1]
        open_risks = (
            self._db.scalar(
                select(func.count(Risk.id)).where(
                    Risk.company_id == company_id,
                    Risk.status.in_([RiskStatus.OPEN, RiskStatus.MITIGATING]),
                )
            )
            or 0
        )
        return {
            "goal_progress": goal_progress,
            "risk_distribution": risk_counts,
            "open_risks": open_risks,
        }

    def full_analytics(self, company_id: UUID) -> dict[str, Any]:
        return {
            "workforce": self.workforce_analytics(company_id),
            "operations": self.operations_analytics(company_id),
            "reliability": self.reliability_analytics(company_id),
            "finance": self.finance_analytics(company_id),
            "strategy": self.strategy_analytics(company_id),
        }


class ForecastService:
    """Deterministic forecasts using linear extrapolation (§56).

    Budget projection: daily burn rate × 30 = projected month-end spend.
    Goal completion: linear extrapolation of progress over elapsed time.
    No autonomous strategy generation.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def budget_forecast(self, company_id: UUID) -> dict[str, Any]:
        """Project month-end spend from current daily burn rate."""
        budget = self._db.execute(
            select(Budget).where(
                Budget.company_id == company_id,
                Budget.scope_type == GoalScopeType.COMPANY,
            )
        ).scalar_one_or_none()
        if budget is None or budget.monthly_limit <= 0:
            return {"projected_spend": 0.0, "projected_utilization": 0.0}
        days_elapsed = max(1, (datetime.now(UTC) - budget.period_start).days)
        daily_rate = budget.spent / days_elapsed
        days_in_period = max(1, (budget.period_end - budget.period_start).days)
        projected = daily_rate * days_in_period
        utilization = (projected / budget.monthly_limit) * 100
        return {
            "company_id": str(company_id),
            "current_spend": round(budget.spent, 2),
            "daily_burn_rate": round(daily_rate, 2),
            "days_elapsed": days_elapsed,
            "projected_month_end_spend": round(projected, 2),
            "projected_utilization_pct": round(utilization, 2),
            "monthly_limit": budget.monthly_limit,
            "on_track": projected <= budget.monthly_limit,
        }

    def goal_forecast(self, goal_id: UUID) -> dict[str, Any]:
        """Project goal completion date from current progress rate."""
        goal = self._db.get(OrgGoal, goal_id)
        if goal is None:
            return {"error": "Goal not found"}
        days_elapsed = max(1, (datetime.now(UTC) - goal.created_at).days)
        progress_rate = goal.progress / days_elapsed  # per day
        if progress_rate <= 0:
            return {
                "goal_id": str(goal_id),
                "current_progress": goal.progress,
                "projected_complete": False,
                "estimated_days_remaining": None,
            }
        remaining = max(0.0, 1.0 - goal.progress)
        days_remaining = remaining / progress_rate if progress_rate else None
        projected_completion = (
            datetime.now(UTC) + timedelta(days=days_remaining)
            if days_remaining is not None
            else None
        )
        return {
            "goal_id": str(goal_id),
            "current_progress": round(goal.progress * 100, 2),
            "daily_progress_rate": round(progress_rate * 100, 4),
            "days_elapsed": days_elapsed,
            "estimated_days_remaining": (
                round(days_remaining, 1) if days_remaining is not None else None
            ),
            "projected_completion_date": (
                projected_completion.isoformat() if projected_completion else None
            ),
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
            "on_track": (
                goal.deadline is not None
                and projected_completion is not None
                and projected_completion <= goal.deadline
            )
            if goal.deadline is not None
            else None,
        }
