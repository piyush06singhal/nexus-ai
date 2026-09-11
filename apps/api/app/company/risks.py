"""AI Company Layer — risk management.

Tracks organizational risks with severity, probability, impact, mitigation
plans, and status. Risks are scoped to company or department level and owned
by an employee. The severity ordering (critical > high > medium > low) drives
prioritization in the health dashboard and alerts (§47-48, §70).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger
from app.db.models.company import (
    GoalScopeType,
    Risk,
    RiskStatus,
)

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class RiskManager:
    """Create, update, and manage organizational risks."""

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
        description: str | None = None,
        severity: str = "medium",
        probability: float | None = None,
        impact: str | None = None,
        owner_id: UUID | None = None,
        mitigation: str | None = None,
    ) -> Risk:
        if severity not in _SEVERITY_RANK:
            raise ValueError(f"Invalid severity '{severity}'. Must be: {list(_SEVERITY_RANK)}")
        risk = Risk(
            company_id=company_id,
            scope_type=scope_type,
            scope_id=scope_id,
            title=title,
            description=description,
            severity=severity,
            probability=probability,
            impact=impact,
            owner_id=owner_id,
            status=RiskStatus.OPEN,
            mitigation=mitigation,
        )
        self._db.add(risk)
        self._db.flush()
        self.events.log(
            actor="system",
            action="risk_created",
            company_id=company_id,
            target_type="risk",
            target_id=risk.id,
            details={"title": title, "severity": severity},
            outcome="success",
        )
        self._db.commit()
        return risk

    def get(self, risk_id: UUID) -> Risk | None:
        return self._db.get(Risk, risk_id)

    def list_(
        self,
        company_id: UUID,
        *,
        scope_type: GoalScopeType | None = None,
        status: RiskStatus | None = None,
        severity: str | None = None,
    ) -> list[Risk]:
        stmt = select(Risk).where(Risk.company_id == company_id).order_by(Risk.created_at.desc())
        if scope_type is not None:
            stmt = stmt.where(Risk.scope_type == scope_type)
        if status is not None:
            stmt = stmt.where(Risk.status == status)
        if severity is not None:
            stmt = stmt.where(Risk.severity == severity)
        return list(self._db.execute(stmt).scalars().all())

    def update_status(self, risk_id: UUID, status: RiskStatus) -> Risk:
        risk = self._db.get(Risk, risk_id)
        if risk is None:
            raise ValueError(f"Risk {risk_id} not found")
        risk.status = status
        self._db.flush()
        self.events.log(
            actor="system",
            action="risk_status_changed",
            company_id=risk.company_id,
            target_type="risk",
            target_id=risk.id,
            details={"new_status": status.value},
            outcome="success",
        )
        self._db.commit()
        return risk

    def update_mitigation(self, risk_id: UUID, mitigation: str) -> Risk:
        risk = self._db.get(Risk, risk_id)
        if risk is None:
            raise ValueError(f"Risk {risk_id} not found")
        risk.mitigation = mitigation
        self._db.flush()
        self._db.commit()
        return risk

    def update_severity(self, risk_id: UUID, severity: str) -> Risk:
        if severity not in _SEVERITY_RANK:
            raise ValueError(f"Invalid severity '{severity}'")
        risk = self._db.get(Risk, risk_id)
        if risk is None:
            raise ValueError(f"Risk {risk_id} not found")
        risk.severity = severity
        self._db.flush()
        self._db.commit()
        return risk

    def top_risks(self, company_id: UUID, *, limit: int = 5) -> list[Risk]:
        """Return the top ``limit`` most severe open risks."""
        open_risks = self.list_(company_id, status=RiskStatus.OPEN)
        open_risks.sort(key=lambda r: _SEVERITY_RANK.get(r.severity, 0), reverse=True)
        return open_risks[:limit]

    def to_dict(self, risk: Risk) -> dict[str, Any]:
        return {
            "id": str(risk.id),
            "company_id": str(risk.company_id),
            "scope_type": risk.scope_type.value,
            "scope_id": str(risk.scope_id),
            "title": risk.title,
            "description": risk.description,
            "severity": risk.severity,
            "probability": risk.probability,
            "impact": risk.impact,
            "owner_id": str(risk.owner_id) if risk.owner_id else None,
            "status": risk.status.value,
            "mitigation": risk.mitigation,
            "created_at": risk.created_at.isoformat() if risk.created_at else None,
            "updated_at": risk.updated_at.isoformat() if risk.updated_at else None,
        }
