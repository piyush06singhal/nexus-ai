"""AI Company Layer — KPI service.

KPIs are computed server-side from authoritative NEXUS data (tasks, executions,
verification, recovery, evaluations, budgets, goals). Values are never accepted
from the client. Each :class:`KPI` names a ``source_metric``; :meth:`KPIService.
recompute` resolves the authoritative value for that metric across the KPI's
scope (company / department / employee), persists it to ``kpi_values``, and
computes variance vs target and trend vs the previous reading.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.company import (
    KPI,
    GoalScopeType,
    KpiCategory,
    KpiValue,
    OrgGoal,
)
from app.db.models.employee import AIEmployee, EmployeeBudget
from app.db.models.execution import AgentExecution
from app.db.models.reliability import RecoveryAttempt, VerificationResult
from app.db.models.task import Task, TaskStatus

# Source metric → (category, unit) registry used to validate KPI definitions.
SOURCE_METRICS: dict[str, tuple[str, str | None]] = {
    "task_success_rate": (KpiCategory.QUALITY.value, "%"),
    "verification_rate": (KpiCategory.RELIABILITY.value, "%"),
    "recovery_rate": (KpiCategory.RELIABILITY.value, "%"),
    "failure_rate": (KpiCategory.RELIABILITY.value, "%"),
    "task_volume": (KpiCategory.PRODUCTIVITY.value, "tasks"),
    "completed_tasks": (KpiCategory.PRODUCTIVITY.value, "tasks"),
    "average_latency_ms": (KpiCategory.SPEED.value, "ms"),
    "budget_utilization": (KpiCategory.COST.value, "%"),
    "total_cost": (KpiCategory.COST.value, "currency"),
    "employee_utilization": (KpiCategory.RESOURCE_UTILIZATION.value, "%"),
    "goal_progress": (KpiCategory.GOAL_PROGRESS.value, "%"),
    "verification_volume": (KpiCategory.OPERATIONAL.value, "runs"),
    "active_employees": (KpiCategory.OPERATIONAL.value, "employees"),
}


class KPIService:
    """Define KPIs and recompute their values from authoritative data."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── CRUD ─────────────────────────────────────────────────────────

    def create(
        self,
        *,
        company_id: UUID,
        scope_type: GoalScopeType,
        scope_id: UUID,
        name: str,
        source_metric: str,
        category: KpiCategory | None = None,
        description: str | None = None,
        target: float | None = None,
        unit: str | None = None,
        owner_id: UUID | None = None,
        frequency: str | None = None,
        formula: dict[str, Any] | None = None,
    ) -> KPI:
        """Create a KPI definition tied to an authoritative source metric."""
        if source_metric not in SOURCE_METRICS:
            raise ValueError(
                f"Unknown source_metric '{source_metric}'. "
                f"Valid: {', '.join(sorted(SOURCE_METRICS))}"
            )
        default_category, default_unit = SOURCE_METRICS[source_metric]
        kpi = KPI(
            company_id=company_id,
            scope_type=scope_type,
            scope_id=scope_id,
            name=name,
            description=description,
            category=category or KpiCategory(default_category),
            source_metric=source_metric,
            target=target,
            unit=unit or default_unit,
            owner_id=owner_id,
            frequency=frequency,
            formula=json.dumps(formula) if formula else None,
        )
        self._db.add(kpi)
        self._db.commit()
        return kpi

    def get(self, kpi_id: UUID) -> KPI | None:
        return self._db.get(KPI, kpi_id)

    def list_(self, company_id: UUID) -> list[KPI]:
        stmt = select(KPI).where(KPI.company_id == company_id).order_by(KPI.category, KPI.name)
        return list(self._db.execute(stmt).scalars().all())

    # ── Scope resolution ─────────────────────────────────────────────

    def _scope_agent_ids(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> list[UUID]:
        """Return the backing agent ids for the KPI's scope."""
        if scope_type == GoalScopeType.EMPLOYEE:
            emp = self._db.get(AIEmployee, scope_id)
            return [emp.agent_id] if emp is not None and emp.agent_id is not None else []
        from app.db.models.company import OrganizationalMembership

        stmt = select(OrganizationalMembership).where(
            OrganizationalMembership.company_id == company_id
        )
        if scope_type == GoalScopeType.DEPARTMENT:
            # Include the department + its subtree.
            dept_ids = self._department_subtree(scope_id)
            stmt = stmt.where(OrganizationalMembership.department_id.in_(dept_ids))
        memberships = list(self._db.execute(stmt).scalars())
        emp_ids = [m.employee_id for m in memberships]
        if not emp_ids:
            return []
        emps = list(
            self._db.execute(select(AIEmployee).where(AIEmployee.id.in_(emp_ids))).scalars()
        )
        return [e.agent_id for e in emps if e.agent_id is not None]

    def _department_subtree(self, department_id: UUID) -> list[UUID]:
        from app.db.models.company import Department

        result = [department_id]
        frontier = [department_id]
        while frontier:
            parent = frontier.pop(0)
            kids = [
                d.id
                for d in self._db.execute(
                    select(Department).where(Department.parent_department_id == parent)
                ).scalars()
            ]
            result.extend(kids)
            frontier.extend(kids)
        return result

    # ── Computation ───────────────────────────────────────────────────

    def compute_value(self, kpi: KPI, scope_type: GoalScopeType, scope_id: UUID) -> float | int:
        """Compute the authoritative value for a KPI's source metric."""
        method = getattr(self, f"_metric_{kpi.source_metric}")
        return method(kpi.company_id, scope_type, scope_id)

    def recompute(self, kpi: KPI, *, period_label: str | None = None) -> KpiValue:
        """Recompute a KPI's value, persist a reading, and compute trend."""
        value = self.compute_value(kpi, kpi.scope_type, kpi.scope_id)
        variance = None
        if kpi.target is not None:
            variance = round(float(value) - kpi.target, 4)

        previous = self._latest_value(kpi.id)
        trend = "flat"
        if previous is not None:
            if value > previous + 1e-9:
                trend = "improving"
            elif value < previous - 1e-9:
                trend = "declining"

        reading = KpiValue(
            kpi_id=kpi.id,
            value=float(value),
            variance=variance,
            trend=trend,
            period_label=period_label or datetime.now(UTC).strftime("%Y-%m-%d"),
        )
        self._db.add(reading)
        self._db.commit()
        return reading

    def recompute_all(self, company_id: UUID) -> list[KpiValue]:
        """Recompute every KPI for a company."""
        readings = []
        for kpi in self.list_(company_id):
            readings.append(self.recompute(kpi))
        return readings

    def _latest_value(self, kpi_id: UUID) -> float | None:
        stmt = (
            select(KpiValue).where(KpiValue.kpi_id == kpi_id).order_by(KpiValue.recorded_at.desc())
        )
        prev = self._db.execute(stmt).scalars().first()
        return prev.value if prev is not None else None

    def readings(self, kpi_id: UUID, *, limit: int = 30) -> list[KpiValue]:
        stmt = (
            select(KpiValue)
            .where(KpiValue.kpi_id == kpi_id)
            .order_by(KpiValue.recorded_at.desc())
            .limit(limit)
        )
        return list(self._db.execute(stmt).scalars().all())

    def snapshot(self, kpi: KPI) -> dict[str, Any]:
        """A KPI snapshot: current/history/target/variance/trend/scope."""
        readings = self.readings(kpi.id, limit=60)
        current = readings[0] if readings else None
        return {
            "id": str(kpi.id),
            "company_id": str(kpi.company_id),
            "scope_type": kpi.scope_type.value,
            "scope_id": str(kpi.scope_id),
            "name": kpi.name,
            "description": kpi.description,
            "category": kpi.category.value,
            "source_metric": kpi.source_metric,
            "target": kpi.target,
            "unit": kpi.unit,
            "owner_id": str(kpi.owner_id) if kpi.owner_id else None,
            "frequency": kpi.frequency,
            "current_value": current.value if current else None,
            "variance": current.variance if current else None,
            "trend": current.trend if current else None,
            "recorded_at": (
                current.recorded_at.isoformat() if current and current.recorded_at else None
            ),
            "history": [
                {
                    "value": r.value,
                    "variance": r.variance,
                    "trend": r.trend,
                    "period_label": r.period_label,
                    "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                }
                for r in readings
            ],
        }

    # ── Metric implementations (authoritative sources) ───────────────

    def _metric_task_success_rate(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> float:
        completed, failed = self._task_counts(company_id, scope_type, scope_id)
        total = completed + failed
        return round((completed / total) * 100, 2) if total else 0.0

    def _metric_failure_rate(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> float:
        completed, failed = self._task_counts(company_id, scope_type, scope_id)
        total = completed + failed
        return round((failed / total) * 100, 2) if total else 0.0

    def _metric_completed_tasks(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> int:
        completed, _ = self._task_counts(company_id, scope_type, scope_id)
        return completed

    def _metric_task_volume(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> int:
        agent_ids = self._scope_agent_ids(company_id, scope_type, scope_id)
        if not agent_ids:
            return 0
        stmt = select(func.count(Task.id)).where(Task.assigned_agent_id.in_(agent_ids))
        return int(self._db.scalar(stmt) or 0)

    def _task_counts(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> tuple[int, int]:
        agent_ids = self._scope_agent_ids(company_id, scope_type, scope_id)
        if not agent_ids:
            return 0, 0
        stmt = (
            select(Task.status, func.count(Task.id))
            .where(Task.assigned_agent_id.in_(agent_ids))
            .group_by(Task.status)
        )
        completed = failed = 0
        for status, count in self._db.execute(stmt):
            try:
                s = status.value if hasattr(status, "value") else status
            except AttributeError:
                s = status
            if s == TaskStatus.COMPLETED.value:
                completed = count
            elif s == TaskStatus.FAILED.value:
                failed = count
        return completed, failed

    def _metric_verification_rate(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> float:
        passes, failures, _ = self._verification_counts(company_id, scope_type, scope_id)
        total = passes + failures
        return round((passes / total) * 100, 2) if total else 0.0

    def _metric_verification_volume(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> int:
        _p, _f, total = self._verification_counts(company_id, scope_type, scope_id)
        return total

    def _verification_counts(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> tuple[int, int, int]:
        agent_ids = self._scope_agent_ids(company_id, scope_type, scope_id)
        if not agent_ids:
            return 0, 0, 0
        stmt = (
            select(VerificationResult.status, func.count(VerificationResult.id))
            .join(
                AgentExecution,
                AgentExecution.id == VerificationResult.execution_id,
            )
            .where(AgentExecution.agent_id.in_(agent_ids))
            .group_by(VerificationResult.status)
        )
        passes = failures = total = 0
        for status, count in self._db.execute(stmt):
            total += count
            s = status.value if hasattr(status, "value") else status
            if s == "pass":
                passes += count
            elif s == "fail":
                failures += count
        return passes, failures, total

    def _metric_recovery_rate(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> float:
        agent_ids = self._scope_agent_ids(company_id, scope_type, scope_id)
        if not agent_ids:
            return 0.0
        stmt = (
            select(RecoveryAttempt.outcome, func.count(RecoveryAttempt.id))
            .join(
                AgentExecution,
                AgentExecution.id == RecoveryAttempt.execution_id,
            )
            .where(AgentExecution.agent_id.in_(agent_ids))
            .group_by(RecoveryAttempt.outcome)
        )
        recovered = total = 0
        for outcome, count in self._db.execute(stmt):
            total += count
            o = outcome.value if hasattr(outcome, "value") else outcome
            if o == "recovered":
                recovered += count
        return round((recovered / total) * 100, 2) if total else 0.0

    def _metric_average_latency_ms(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> float:
        agent_ids = self._scope_agent_ids(company_id, scope_type, scope_id)
        if not agent_ids:
            return 0.0
        stmt = select(func.avg(AgentExecution.latency_ms)).where(
            AgentExecution.agent_id.in_(agent_ids)
        )
        avg = self._db.scalar(stmt)
        return round(float(avg), 2) if avg else 0.0

    def _metric_budget_utilization(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> float:
        from app.db.models.company import Budget

        if scope_type == GoalScopeType.EMPLOYEE:
            emp_budget = self._db.execute(
                select(EmployeeBudget).where(EmployeeBudget.employee_id == scope_id)
            ).scalar_one_or_none()
            if emp_budget is None or not emp_budget.monthly_limit:
                return 0.0
            return round((emp_budget.cost_used / emp_budget.monthly_limit) * 100, 2)
        budget = self._db.execute(
            select(Budget).where(
                Budget.company_id == company_id,
                Budget.scope_type == scope_type,
                Budget.scope_id == scope_id,
            )
        ).scalar_one_or_none()
        if budget is None or not budget.monthly_limit:
            return 0.0
        return round((budget.spent / budget.monthly_limit) * 100, 2)

    def _metric_total_cost(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> float:
        if scope_type == GoalScopeType.EMPLOYEE:
            emp_budget = self._db.execute(
                select(EmployeeBudget).where(EmployeeBudget.employee_id == scope_id)
            ).scalar_one_or_none()
            return round(emp_budget.cost_used or 0.0, 2) if emp_budget else 0.0
        from app.db.models.company import Budget

        budget = self._db.execute(
            select(Budget).where(
                Budget.company_id == company_id,
                Budget.scope_type == scope_type,
                Budget.scope_id == scope_id,
            )
        ).scalar_one_or_none()
        return round(budget.spent or 0.0, 2) if budget else 0.0

    def _metric_employee_utilization(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> float:

        agent_ids = self._scope_agent_ids(company_id, scope_type, scope_id)
        if not agent_ids:
            return 0.0
        from sqlalchemy import func as _f

        stmt = select(
            _f.count(Task.id).filter(Task.status == TaskStatus.IN_PROGRESS),
            _f.count(Task.id).filter(Task.status == TaskStatus.QUEUED),
        ).where(Task.assigned_agent_id.in_(agent_ids))
        in_progress, queued = self._db.execute(stmt).one()
        active = (in_progress or 0) + (queued or 0)
        capacity = max(1, 5 * len(agent_ids))
        return round((active / capacity) * 100, 2) if capacity else 0.0

    def _metric_active_employees(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> int:
        from app.db.models.company import OrganizationalMembership

        stmt = select(func.count(OrganizationalMembership.id)).where(
            OrganizationalMembership.company_id == company_id
        )
        return int(self._db.scalar(stmt) or 0)

    def _metric_goal_progress(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> float:
        stmt = select(func.avg(OrgGoal.progress)).where(
            OrgGoal.company_id == company_id,
            OrgGoal.scope_type == scope_type,
            OrgGoal.scope_id == scope_id,
        )
        avg = self._db.scalar(stmt)
        return round(float(avg) * 100, 2) if avg is not None else 0.0
