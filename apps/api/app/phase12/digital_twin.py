"""Company digital twin — a versioned, read-only mirror of a real company.

``CompanyDigitalTwin`` reads Phase 8 company/departments/employees/agents/goals/
kpis/budgets into a ``simulation_snapshots`` row (JSON) under a name + model
version. It **never mutates the source company** — the snapshot is derived data
and all readers are pure SELECTs. Docstring caveat: modeled scenarios, not
guaranteed predictions.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.company import KPI, Company, OrgGoal
from app.db.models.employee import AIEmployee
from app.db.models.phase12 import SimulationSnapshot

_DISCLAIMER = (
    "This is a modeled digital-twin snapshot, not a prediction. Scenarios built "
    "on it produce modeled estimates only — they never represent guarantees "
    "about the real company."
)


class DigitalTwinError(ValueError):
    """The requested company could not be twinned."""


class CompanyDigitalTwin:
    """Twins a company into a versioned read-only snapshot."""

    def __init__(
        self,
        *,
        name: str = "nexus-twin-v1",
        model_version: str = "1.0",
    ) -> None:
        self.name = name
        self.model_version = model_version

    # ── Snapshot ──────────────────────────────────────────────────────

    def snapshot(
        self, db: Session, company_id: UUID, created_by: UUID | None = None
    ) -> SimulationSnapshot:
        """Build and persist a versioned snapshot row. Read-only vs the company."""
        company = db.get(Company, company_id)
        if company is None:
            raise DigitalTwinError(f"Company {company_id} not found")
        data = self._capture(db, company)
        snap = SimulationSnapshot(
            source_company_id=company_id,
            company_id=company_id,
            name=self.name,
            model_version=self.model_version,
            snapshot_json=data,
            created_by=created_by,
        )
        db.add(snap)
        db.commit()
        return snap

    def _capture(self, db: Session, company: Company) -> dict[str, Any]:
        """Serialize the twin (pure reads). Never mutates source rows."""
        employees = self._employees(db, company.id)
        departments = self._departments(db, company.id)
        goals = self._goals(db, company.id)
        kpis = self._kpis(db, company.id)
        return {
            "disclaimer": _DISCLAIMER,
            "company": {
                "id": str(company.id),
                "name": company.name,
                "status": _value(company.status),
                "industry": company.industry,
            },
            "departments": departments,
            "employees": employees,
            "agents": self._backing_agents(db, employees),
            "goals": goals,
            "kpis": kpis,
            "counts": {
                "departments": len(departments),
                "employees": len(employees),
                "agents": len(employees),
                "goals": len(goals),
                "kpis": len(kpis),
            },
        }

    # ── Readers (pure SELECTs) ────────────────────────────────────────

    def _departments(self, db: Session, company_id: UUID) -> list[dict[str, Any]]:
        from app.db.models.company import Department

        rows = list(
            db.execute(select(Department).where(Department.company_id == company_id)).scalars()
        )
        return [
            {
                "id": str(d.id),
                "name": d.name,
                "status": _value(d.status),
                "parent_department_id": str(d.parent_department_id)
                if getattr(d, "parent_department_id", None)
                else None,
            }
            for d in rows
        ]

    def _employees(self, db: Session, company_id: UUID) -> list[dict[str, Any]]:
        from app.db.models.company import OrganizationalMembership

        memberships = list(
            db.execute(
                select(OrganizationalMembership).where(
                    OrganizationalMembership.company_id == company_id
                )
            ).scalars()
        )
        emp_ids = [m.employee_id for m in memberships if m.employee_id is not None]
        if not emp_ids:
            return []
        emps = list(db.execute(select(AIEmployee).where(AIEmployee.id.in_(emp_ids))).scalars())
        return [
            {
                "id": str(e.id),
                "name": e.name,
                "role": getattr(e, "role", None),
                "status": _value(getattr(e, "status", None)),
                "agent_id": str(e.agent_id) if getattr(e, "agent_id", None) else None,
            }
            for e in emps
        ]

    def _backing_agents(self, db: Session, employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from app.db.models.agent import Agent

        agent_ids = [UUID(a["agent_id"]) for a in employees if a["agent_id"]]
        if not agent_ids:
            return []
        agents = list(db.execute(select(Agent).where(Agent.id.in_(agent_ids))).scalars())
        return [
            {
                "id": str(a.id),
                "name": a.name,
                "status": _value(a.status),
                "role": getattr(a, "role", None) or getattr(a, "model", None) or None,
            }
            for a in agents
        ]

    def _goals(self, db: Session, company_id: UUID) -> list[dict[str, Any]]:
        rows = list(db.execute(select(OrgGoal).where(OrgGoal.company_id == company_id)).scalars())
        return [
            {
                "id": str(g.id),
                "name": getattr(g, "name", None),
                "scope_type": _value(getattr(g, "scope_type", None)),
                "progress": getattr(g, "progress", None),
                "status": _value(getattr(g, "status", None)),
            }
            for g in rows
        ]

    def _kpis(self, db: Session, company_id: UUID) -> list[dict[str, Any]]:
        rows = list(db.execute(select(KPI).where(KPI.company_id == company_id)).scalars())
        return [
            {
                "id": str(k.id),
                "name": k.name,
                "category": _value(getattr(k, "category", None)),
                "source_metric": getattr(k, "source_metric", None),
                "target": getattr(k, "target", None),
                "unit": getattr(k, "unit", None),
                "scope_type": _value(getattr(k, "scope_type", None)),
                "scope_id": str(k.scope_id) if getattr(k, "scope_id", None) else None,
            }
            for k in rows
        ]


def _value(x: Any) -> Any:
    """Resolve an enum value to its string (or passthrough)."""
    if x is None:
        return None
    return getattr(x, "value", x)
