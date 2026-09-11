"""AI Company Layer — alert management and company health scoring.

Alerts are generated from threshold rules (§48): budget spend >80% triggers
a warning, verification rate <85% triggers a reliability alert, and goals that
fall behind schedule trigger at-risk alerts. :class:`CompanyHealth` computes a
holistic health score across six dimensions (execution, quality, reliability,
cost, goal progress, risk posture), each backed by real operational data (§47).
The ``explain`` method returns a human-readable breakdown suitable for the
dashboard and demo (§85).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger
from app.db.models.company import (
    Alert,
    AlertSeverity,
    AlertStatus,
    Budget,
    GoalScopeType,
    GoalStatusOrg,
    OrgGoal,
    Risk,
    RiskStatus,
)
from app.db.models.employee import AIEmployee
from app.db.models.execution import AgentExecution
from app.db.models.reliability import VerificationResult
from app.db.models.task import Task, TaskStatus


class AlertManager:
    """Generate, persist, and manage operational alerts."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)

    def create(
        self,
        *,
        company_id: UUID,
        scope_type: GoalScopeType,
        scope_id: UUID,
        title: str,
        severity: AlertSeverity,
        category: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> Alert:
        alert = Alert(
            company_id=company_id,
            scope_type=scope_type,
            scope_id=scope_id,
            title=title,
            severity=severity,
            category=category,
            message=message,
            status=AlertStatus.ACTIVE,
            payload=json.dumps(payload) if payload else None,
        )
        self._db.add(alert)
        self._db.flush()
        self.events.log(
            actor="system",
            action="alert_created",
            company_id=company_id,
            target_type="alert",
            target_id=alert.id,
            details={"title": title, "severity": severity.value, "category": category},
            outcome="success",
        )
        self._db.commit()
        return alert

    def get(self, alert_id: UUID) -> Alert | None:
        return self._db.get(Alert, alert_id)

    def list_(
        self,
        company_id: UUID,
        *,
        severity: AlertSeverity | None = None,
        status: AlertStatus | None = None,
        category: str | None = None,
    ) -> list[Alert]:
        stmt = select(Alert).where(Alert.company_id == company_id).order_by(Alert.created_at.desc())
        if severity is not None:
            stmt = stmt.where(Alert.severity == severity)
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        if category is not None:
            stmt = stmt.where(Alert.category == category)
        return list(self._db.execute(stmt).scalars().all())

    def acknowledge(self, alert_id: UUID) -> Alert:
        alert = self._db.get(Alert, alert_id)
        if alert is None:
            raise ValueError(f"Alert {alert_id} not found")
        alert.status = AlertStatus.ACKNOWLEDGED
        self._db.commit()
        return alert

    def resolve(self, alert_id: UUID) -> Alert:
        alert = self._db.get(Alert, alert_id)
        if alert is None:
            raise ValueError(f"Alert {alert_id} not found")
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)
        self._db.commit()
        return alert

    def to_dict(self, alert: Alert) -> dict[str, Any]:
        return {
            "id": str(alert.id),
            "company_id": str(alert.company_id),
            "scope_type": alert.scope_type.value,
            "scope_id": str(alert.scope_id),
            "title": alert.title,
            "severity": alert.severity.value,
            "category": alert.category,
            "message": alert.message,
            "status": alert.status.value,
            "payload": json.loads(alert.payload) if alert.payload else None,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        }

    # ── Threshold-based alert generation ───────────────────────────────

    def generate_alerts(self, company_id: UUID) -> list[Alert]:
        """Run all threshold rules and create alerts for violations."""
        alerts: list[Alert] = []
        alerts.extend(self._check_budget_thresholds(company_id))
        alerts.extend(self._check_verification_thresholds(company_id))
        alerts.extend(self._check_goal_at_risk(company_id))
        return alerts

    def _check_budget_thresholds(self, company_id: UUID) -> list[Alert]:
        """Spend >80% of budget → budget warning alert (§48)."""
        alerts: list[Alert] = []
        budgets = list(
            self._db.execute(select(Budget).where(Budget.company_id == company_id)).scalars()
        )
        for budget in budgets:
            if budget.monthly_limit <= 0:
                continue
            utilization = (budget.spent / budget.monthly_limit) * 100
            if utilization > 80:
                alert = Alert(
                    company_id=company_id,
                    scope_type=budget.scope_type,
                    scope_id=budget.scope_id,
                    title=f"Budget utilization at {utilization:.0f}%",
                    severity=(
                        AlertSeverity.CRITICAL if utilization > 95 else AlertSeverity.WARNING
                    ),
                    category="budget",
                    message=(
                        f"Budget for {budget.scope_type.value} scope is at "
                        f"{utilization:.1f}% utilization (${budget.spent:.2f} / "
                        f"${budget.monthly_limit:.2f})"
                    ),
                    status=AlertStatus.ACTIVE,
                    payload=json.dumps(
                        {
                            "budget_id": str(budget.id),
                            "utilization_pct": round(utilization, 2),
                            "spent": budget.spent,
                            "limit": budget.monthly_limit,
                        }
                    ),
                )
                self._db.add(alert)
                alerts.append(alert)
        if alerts:
            self._db.flush()
            for alert in alerts:
                self.events.log(
                    actor="system",
                    action="alert_generated",
                    company_id=company_id,
                    target_type="alert",
                    target_id=alert.id,
                    details={"category": "budget", "severity": alert.severity.value},
                    outcome="success",
                )
            self._db.commit()
        return alerts

    def _check_verification_thresholds(self, company_id: UUID) -> list[Alert]:
        """Verification rate <85% → reliability alert (§48)."""
        from app.db.models.company import OrganizationalMembership

        alerts: list[Alert] = []
        member_emp_ids = list(
            self._db.execute(
                select(OrganizationalMembership.employee_id).where(
                    OrganizationalMembership.company_id == company_id
                )
            ).scalars()
        )
        if not member_emp_ids:
            return []
        emp_ids = [
            eid
            for eid in self._db.execute(
                select(AIEmployee.id).where(AIEmployee.id.in_(member_emp_ids))
            ).scalars()
        ]
        if not emp_ids:
            return []
        agent_ids = list(
            self._db.execute(
                select(AIEmployee.agent_id).where(
                    AIEmployee.id.in_(emp_ids), AIEmployee.agent_id.is_not(None)
                )
            ).scalars()
        )
        if not agent_ids:
            return []

        total_stmt = (
            select(func.count(VerificationResult.id))
            .join(AgentExecution, AgentExecution.id == VerificationResult.execution_id)
            .where(AgentExecution.agent_id.in_(agent_ids))
        )
        total = self._db.scalar(total_stmt) or 0
        if total == 0:
            return []
        pass_stmt = (
            select(func.count(VerificationResult.id))
            .join(AgentExecution, AgentExecution.id == VerificationResult.execution_id)
            .where(
                AgentExecution.agent_id.in_(agent_ids),
                VerificationResult.status == "pass",
            )
        )
        passes = self._db.scalar(pass_stmt) or 0
        rate = (passes / total) * 100
        if rate < 85:
            alert = Alert(
                company_id=company_id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company_id,
                title=f"Verification rate below threshold: {rate:.1f}%",
                severity=(AlertSeverity.CRITICAL if rate < 70 else AlertSeverity.WARNING),
                category="reliability",
                message=(
                    f"Company verification rate is {rate:.1f}% "
                    f"({passes}/{total} pass), below 85% threshold"
                ),
                status=AlertStatus.ACTIVE,
                payload=json.dumps(
                    {
                        "verification_rate": round(rate, 2),
                        "passes": passes,
                        "total": total,
                    }
                ),
            )
            self._db.add(alert)
            self._db.flush()
            self.events.log(
                actor="system",
                action="alert_generated",
                company_id=company_id,
                target_type="alert",
                target_id=alert.id,
                details={"category": "reliability", "severity": alert.severity.value},
                outcome="success",
            )
            self._db.commit()
            alerts.append(alert)
        return alerts

    def _check_goal_at_risk(self, company_id: UUID) -> list[Alert]:
        """Goals with progress <20% when halfway to deadline → at-risk alert."""
        alerts: list[Alert] = []
        now = datetime.now(UTC)
        goals = list(
            self._db.execute(
                select(OrgGoal).where(
                    OrgGoal.company_id == company_id,
                    OrgGoal.status.in_([GoalStatusOrg.ACTIVE, GoalStatusOrg.NOT_STARTED]),
                )
            ).scalars()
        )
        for goal in goals:
            if goal.deadline is None:
                continue
            total_days = (goal.deadline - goal.created_at).days or 1
            elapsed_days = (now - goal.created_at).days
            if elapsed_days < total_days * 0.5:
                continue  # Not yet halfway
            if goal.progress < 0.20:
                alert = Alert(
                    company_id=company_id,
                    scope_type=goal.scope_type,
                    scope_id=goal.scope_id,
                    title=f"Goal behind schedule: {goal.title}",
                    severity=AlertSeverity.WARNING,
                    category="goal_progress",
                    message=(
                        f"Goal '{goal.title}' is {goal.progress * 100:.0f}% complete "
                        f"but {elapsed_days}/{total_days} days have elapsed"
                    ),
                    status=AlertStatus.ACTIVE,
                    payload=json.dumps(
                        {
                            "goal_id": str(goal.id),
                            "progress": goal.progress,
                            "elapsed_days": elapsed_days,
                            "total_days": total_days,
                        }
                    ),
                )
                self._db.add(alert)
                alerts.append(alert)
        if alerts:
            self._db.flush()
            for alert in alerts:
                self.events.log(
                    actor="system",
                    action="alert_generated",
                    company_id=company_id,
                    target_type="alert",
                    target_id=alert.id,
                    details={"category": "goal_progress"},
                    outcome="success",
                )
            self._db.commit()
        return alerts


# ── Company Health ──────────────────────────────────────────────────────


class CompanyHealth:
    """Compute holistic company health across six dimensions (§47).

    Each dimension produces a 0-100 score computed from real data:
      - execution: task success rate
      - quality: verification pass rate
      - reliability: recovery rate
      - cost: budget utilization (inverted — lower utilization is healthier)
      - goal_progress: average goal completion
      - risk_posture: ratio of resolved vs total risks (inverted — fewer open
        high-severity risks is healthier)

    The overall score is the weighted mean: execution(20) + quality(20) +
    reliability(15) + cost(15) + goal_progress(20) + risk_posture(10) = 100.
    """

    WEIGHTS = {
        "execution": 20,
        "quality": 20,
        "reliability": 15,
        "cost": 15,
        "goal_progress": 20,
        "risk_posture": 10,
    }

    def __init__(self, db: Session) -> None:
        self._db = db

    def compute(self, company_id: UUID) -> dict[str, Any]:
        """Compute the full health snapshot for a company."""
        scores = {
            "execution": self._score_execution(company_id),
            "quality": self._score_quality(company_id),
            "reliability": self._score_reliability(company_id),
            "cost": self._score_cost(company_id),
            "goal_progress": self._score_goal_progress(company_id),
            "risk_posture": self._score_risk_posture(company_id),
        }
        overall = sum(scores[dim] * (self.WEIGHTS[dim] / 100) for dim in scores)
        status = "healthy"
        if overall < 50:
            status = "critical"
        elif overall < 75:
            status = "degraded"
        return {
            "company_id": str(company_id),
            "overall_score": round(overall, 2),
            "status": status,
            "dimensions": scores,
            "weights": self.WEIGHTS,
            "computed_at": datetime.now(UTC).isoformat(),
        }

    def explain(self, company_id: UUID) -> dict[str, Any]:
        """Human-readable explanation of the health score (§85 demo)."""
        health = self.compute(company_id)
        explanations: dict[str, str] = {}
        for dim, score in health["dimensions"].items():
            if score >= 80:
                explanations[dim] = f"{dim} is healthy ({score:.0f}/100)"
            elif score >= 60:
                explanations[dim] = f"{dim} needs attention ({score:.0f}/100)"
            else:
                explanations[dim] = f"{dim} is degraded ({score:.0f}/100)"
        return {
            "health": health,
            "explanations": explanations,
        }

    def _member_agent_ids(self, company_id: UUID) -> list[UUID]:
        from app.db.models.company import OrganizationalMembership

        emp_ids = list(
            self._db.execute(
                select(OrganizationalMembership.employee_id).where(
                    OrganizationalMembership.company_id == company_id
                )
            ).scalars()
        )
        if not emp_ids:
            return []
        return [
            aid
            for aid in self._db.execute(
                select(AIEmployee.agent_id).where(
                    AIEmployee.id.in_(emp_ids), AIEmployee.agent_id.is_not(None)
                )
            ).scalars()
        ]

    def _score_execution(self, company_id: UUID) -> float:
        agent_ids = self._member_agent_ids(company_id)
        if not agent_ids:
            return 50.0  # Neutral when no data
        status_counts = self._db.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.assigned_agent_id.in_(agent_ids))
            .group_by(Task.status)
        ).all()
        completed = failed = 0
        for status, count in status_counts:
            s = getattr(status, "value", status)
            if s == TaskStatus.COMPLETED.value:
                completed = count
            elif s == TaskStatus.FAILED.value:
                failed = count
        total = completed + failed
        return round((completed / total) * 100, 2) if total else 50.0

    def _score_quality(self, company_id: UUID) -> float:
        agent_ids = self._member_agent_ids(company_id)
        if not agent_ids:
            return 50.0
        total = (
            self._db.scalar(
                select(func.count(VerificationResult.id))
                .join(AgentExecution, AgentExecution.id == VerificationResult.execution_id)
                .where(AgentExecution.agent_id.in_(agent_ids))
            )
            or 0
        )
        if total == 0:
            return 50.0
        passes = (
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
        return round((passes / total) * 100, 2)

    def _score_reliability(self, company_id: UUID) -> float:
        from app.db.models.reliability import RecoveryAttempt

        agent_ids = self._member_agent_ids(company_id)
        if not agent_ids:
            return 50.0
        total = (
            self._db.scalar(
                select(func.count(RecoveryAttempt.id))
                .join(AgentExecution, AgentExecution.id == RecoveryAttempt.execution_id)
                .where(AgentExecution.agent_id.in_(agent_ids))
            )
            or 0
        )
        if total == 0:
            return 50.0
        recovered = (
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
        return round((recovered / total) * 100, 2)

    def _score_cost(self, company_id: UUID) -> float:
        """Inverted: lower budget utilization → healthier score."""
        budget = self._db.execute(
            select(Budget).where(
                Budget.company_id == company_id,
                Budget.scope_type == GoalScopeType.COMPANY,
            )
        ).scalar_one_or_none()
        if budget is None or budget.monthly_limit <= 0:
            return 75.0  # No budget = assume reasonable
        utilization = (budget.spent / budget.monthly_limit) * 100
        return round(max(0.0, 100.0 - utilization), 2)

    def _score_goal_progress(self, company_id: UUID) -> float:
        avg = self._db.scalar(
            select(func.avg(OrgGoal.progress)).where(
                OrgGoal.company_id == company_id,
                OrgGoal.scope_type == GoalScopeType.COMPANY,
            )
        )
        return round(float(avg) * 100, 2) if avg is not None else 50.0

    def _score_risk_posture(self, company_id: UUID) -> float:
        """Inverted: more resolved risks → healthier score."""
        total = (
            self._db.scalar(select(func.count(Risk.id)).where(Risk.company_id == company_id)) or 0
        )
        if total == 0:
            return 80.0  # No risks tracked → good
        resolved = (
            self._db.scalar(
                select(func.count(Risk.id)).where(
                    Risk.company_id == company_id,
                    Risk.status.in_([RiskStatus.RESOLVED, RiskStatus.ACCEPTED]),
                )
            )
            or 0
        )
        # Also penalize for open critical risks
        open_critical = (
            self._db.scalar(
                select(func.count(Risk.id)).where(
                    Risk.company_id == company_id,
                    Risk.status == RiskStatus.OPEN,
                    Risk.severity == "critical",
                )
            )
            or 0
        )
        base_score = (resolved / total) * 100
        penalty = min(30, open_critical * 10)  # Up to 30 pts penalty
        return round(max(0.0, base_score - penalty), 2)
