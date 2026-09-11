"""AI Company Layer — performance aggregation.

Aggregates company and department performance from actual operational data
(tasks, verification, recovery, budgets, goals, employee utilization), not from
mock dashboard numbers. Used by the executive dashboard, department interface,
reports, and the KPI service.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.company.departments import DepartmentManager
from app.company.kpis import KPIService
from app.company.membership import MembershipManager
from app.db.models.company import GoalScopeType, OrgGoal
from app.db.models.employee import AIEmployee
from app.db.models.execution import AgentExecution
from app.db.models.reliability import RecoveryAttempt, VerificationResult
from app.db.models.task import Task, TaskStatus


class PerformanceAggregator:
    """Compute company and department performance summaries."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _member_agent_ids(self, company_id: UUID, department_id: UUID | None = None) -> list[UUID]:
        from app.db.models.company import OrganizationalMembership

        stmt = select(OrganizationalMembership).where(
            OrganizationalMembership.company_id == company_id
        )
        if department_id is not None:
            stmt = stmt.where(OrganizationalMembership.department_id == department_id)
        memberships = list(self._db.execute(stmt).scalars())
        emp_ids = [m.employee_id for m in memberships]
        if not emp_ids:
            return []
        emps = list(
            self._db.execute(select(AIEmployee).where(AIEmployee.id.in_(emp_ids))).scalars()
        )
        return [e.agent_id for e in emps if e.agent_id is not None]

    def aggregate(self, company_id: UUID, department_id: UUID | None = None) -> dict[str, Any]:
        """Aggregate performance for a company (or one department)."""
        agent_ids = self._member_agent_ids(company_id, department_id)

        task_volume = 0
        completed = failed = in_progress = queued = 0
        if agent_ids:
            stmt = (
                select(Task.status, func.count(Task.id))
                .where(Task.assigned_agent_id.in_(agent_ids))
                .group_by(Task.status)
            )
            for status, count in self._db.execute(stmt):
                s = getattr(status, "value", status)
                task_volume += count
                if s == TaskStatus.COMPLETED.value:
                    completed = count
                elif s == TaskStatus.FAILED.value:
                    failed = count
                elif s == TaskStatus.IN_PROGRESS.value:
                    in_progress = count
                elif s == TaskStatus.QUEUED.value:
                    queued = count

        success_rate = (
            round((completed / (completed + failed)) * 100, 2) if (completed + failed) else 0.0
        )
        failure_rate = (
            round((failed / (completed + failed)) * 100, 2) if (completed + failed) else 0.0
        )

        # Verification + recovery (scoped via agent executions).
        verification_rate = recovery_rate = 0.0
        verification_total = recovery_total = 0
        verification_pass = recovery_recovered = 0
        if agent_ids:
            vstmt = (
                select(VerificationResult.status, func.count(VerificationResult.id))
                .join(AgentExecution, AgentExecution.id == VerificationResult.execution_id)
                .where(AgentExecution.agent_id.in_(agent_ids))
                .group_by(VerificationResult.status)
            )
            for status, count in self._db.execute(vstmt):
                verification_total += count
                if getattr(status, "value", status) == "pass":
                    verification_pass += count
            verification_rate = (
                round((verification_pass / verification_total) * 100, 2)
                if verification_total
                else 0.0
            )

            rstmt = (
                select(RecoveryAttempt.outcome, func.count(RecoveryAttempt.id))
                .join(AgentExecution, AgentExecution.id == RecoveryAttempt.execution_id)
                .where(AgentExecution.agent_id.in_(agent_ids))
                .group_by(RecoveryAttempt.outcome)
            )
            for outcome, count in self._db.execute(rstmt):
                recovery_total += count
                if getattr(outcome, "value", outcome) == "recovered":
                    recovery_recovered += count
            recovery_rate = (
                round((recovery_recovered / recovery_total) * 100, 2) if recovery_total else 0.0
            )

        # Cost + latency.
        total_cost = 0.0
        avg_latency_ms = 0.0
        if agent_ids:
            cstmt = select(func.coalesce(func.sum(AgentExecution.estimated_cost), 0.0)).where(
                AgentExecution.agent_id.in_(agent_ids)
            )
            total_cost = round(float(self._db.scalar(cstmt) or 0.0), 2)
            lstmt = select(func.avg(AgentExecution.latency_ms)).where(
                AgentExecution.agent_id.in_(agent_ids)
            )
            avg = self._db.scalar(lstmt)
            avg_latency_ms = round(float(avg), 2) if avg else 0.0

        # Goal progress (avg across scoped org goals).
        scope_type = GoalScopeType.DEPARTMENT if department_id else GoalScopeType.COMPANY
        scope_id = department_id if department_id else company_id
        goal_progress = self._goal_progress(company_id, scope_type, scope_id)

        # Employee utilization (active backlog vs capacity).
        utilization = 0.0
        if agent_ids:
            cap = max(1, 5 * len(agent_ids))
            active = in_progress + queued
            utilization = round((active / cap) * 100, 2)

        return {
            "task_volume": task_volume,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "in_progress_tasks": in_progress,
            "queued_tasks": queued,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "verification_rate": verification_rate,
            "recovery_rate": recovery_rate,
            "total_cost": total_cost,
            "average_latency_ms": avg_latency_ms,
            "goal_progress": goal_progress,
            "employee_utilization": utilization,
            "employee_count": len(self._member_employee_ids(company_id, department_id)),
        }

    def _member_employee_ids(
        self, company_id: UUID, department_id: UUID | None = None
    ) -> list[UUID]:
        from app.db.models.company import OrganizationalMembership

        stmt = select(OrganizationalMembership.employee_id).where(
            OrganizationalMembership.company_id == company_id
        )
        if department_id is not None:
            stmt = stmt.where(OrganizationalMembership.department_id == department_id)
        return [r for r in self._db.execute(stmt).scalars()]

    def _goal_progress(self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID) -> float:
        stmt = select(func.avg(OrgGoal.progress)).where(
            OrgGoal.company_id == company_id,
            OrgGoal.scope_type == scope_type,
            OrgGoal.scope_id == scope_id,
        )
        avg = self._db.scalar(stmt)
        return round(float(avg) * 100, 2) if avg is not None else 0.0

    def kpi_summary(self, company_id: UUID) -> list[dict[str, Any]]:
        """Return KPI snapshots for a company (recomputing lazily)."""
        kpis = KPIService(self._db)
        out = []
        for kpi in kpis.list_(company_id):
            out.append(kpis.snapshot(kpi))
        return out

    def executive_dashboard(self, company_id: UUID) -> dict[str, Any]:
        """Compose the executive dashboard row from real aggregates + KPIs."""
        agg = self.aggregate(company_id)
        departments = DepartmentManager(self._db).list_(company_id)
        employees = MembershipManager(self._db).list_employees(company_id)
        goals = list(
            self._db.execute(
                select(OrgGoal).where(
                    OrgGoal.company_id == company_id,
                    OrgGoal.scope_type == GoalScopeType.COMPANY,
                )
            ).scalars()
        )
        active_goals = [g for g in goals if g.status.value in ("active", "at_risk")]
        return {
            "company_id": str(company_id),
            "employees": len(employees),
            "departments": len(departments),
            "active_goals": len(active_goals),
            "task_success_rate": agg["success_rate"],
            "verification_rate": agg["verification_rate"],
            "recovery_rate": agg["recovery_rate"],
            "total_cost": agg["total_cost"],
            "employee_utilization": agg["employee_utilization"],
            "goal_progress": agg["goal_progress"],
            "kpis": self.kpi_summary(company_id),
        }
