"""Resource allocation — budget/capacity/concurrency/tokens across work.

:class:`ResourceAllocator` plans and records allocations against real Phase 8
budgets and capacity limits. It always respects the company's autonomy policy
(``allocate_budget`` may itself require a gate) and the per-budget ``set_allocation``
path — an allocation is a *recorded claim*, never an external purchase, and any
budget mutation goes through :class:`BudgetManager`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.company.budget import BudgetManager
from app.db.models.company import GoalScopeType
from app.db.models.startup import MissionGraphRelation, ResourceAllocation
from app.startup.autonomy import AutonomyService
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.graph import MissionGraphBuilder

_RESOURCE_TYPES = ("budget", "capacity", "concurrency", "tokens", "tools", "time")


class ResourceAllocator:
    """Plan and record resource allocations under governance."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._budgets = BudgetManager(db)
        self._events = StartupEventLogger(db)

    def allocate(
        self,
        *,
        company_id: UUID,
        target_type: str,
        target_id: UUID,
        resource_type: str,
        amount: float,
        unit: str | None = None,
        purpose: dict[str, Any] | None = None,
        actor: str = "cycle",
    ) -> ResourceAllocation:
        """Record an allocation; budget-type allocations reserve real budget."""
        if resource_type not in _RESOURCE_TYPES:
            raise ValueError(f"Unknown resource type '{resource_type}'")
        if amount < 0:
            raise ValueError("Allocation amount cannot be negative")

        # Budget allocations respect the autonomy policy (may require a gate).
        if resource_type == "budget":
            AutonomyService(self._db).enforce(
                "allocate_budget",
                company_id,
                estimated_cost=amount,
                actor=actor,
            )
            budget = self._budgets.ensure_budget(
                company_id, GoalScopeType.COMPANY, company_id, monthly_limit=max(1.0, amount)
            )
            reserved = self._budgets.reserve(budget, amount)
            if not reserved:
                raise ValueError(
                    f"Budget allocation of {amount:.2f} exceeds remaining company budget"
                )

        row = ResourceAllocation(
            company_id=company_id,
            target_type=target_type,
            target_id=target_id,
            resource_type=resource_type,
            amount=amount,
            unit=unit,
            purpose=__import__("json").dumps(purpose) if purpose else None,
            actor=actor,
        )
        self._db.add(row)
        self._db.commit()
        MissionGraphBuilder(self._db).link(
            company_id=company_id,
            source_type="resource_allocation",
            source_id=row.id,
            target_type=target_type,
            target_id=target_id,
            relation=MissionGraphRelation.DEPENDS_ON,
            metadata={"resource_type": resource_type, "amount": amount},
        )
        self._events.log(
            action=StartupEvents.RESOURCE_ALLOCATED,
            company_id=company_id,
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            details={
                "resource_type": resource_type,
                "amount": amount,
                "unit": unit,
                "purpose": purpose,
            },
            outcome="success",
        )
        return row

    def allocate_workload(
        self,
        *,
        company_id: UUID,
        project_id: UUID,
        employee_ids: list[UUID],
        monthly_budget: float,
        actor: str = "cycle",
    ) -> list[dict[str, Any]]:
        """Allocate budget + capacity for a project across its employees."""
        created = []
        created.append(
            self.allocate(
                company_id=company_id,
                target_type="startup_project",
                target_id=project_id,
                resource_type="budget",
                amount=monthly_budget,
                unit="USD/month",
                purpose={"for": "project execution"},
                actor=actor,
            )
        )
        for idx, employee_id in enumerate(employee_ids, start=1):
            row = self.allocate(
                company_id=company_id,
                target_type="employee",
                target_id=employee_id,
                resource_type="capacity",
                amount=1.0,
                unit="work_unit",
                purpose={"project": str(project_id), "index": idx},
                actor=actor,
            )
            created.append(row)
        return [self.to_dict(r) for r in created]

    def history(self, company_id: UUID, *, target_type: str | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import select

        stmt = (
            select(ResourceAllocation)
            .where(ResourceAllocation.company_id == company_id)
            .order_by(ResourceAllocation.created_at.desc())
        )
        if target_type is not None:
            stmt = stmt.where(ResourceAllocation.target_type == target_type)
        return [self.to_dict(r) for r in self._db.execute(stmt).scalars().all()]

    def to_dict(self, row: ResourceAllocation) -> dict[str, Any]:
        def _loads(raw: str | None) -> Any:
            if not raw:
                return None
            try:
                import json

                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw

        return {
            "id": str(row.id),
            "company_id": str(row.company_id),
            "target_type": row.target_type,
            "target_id": str(row.target_id),
            "resource_type": row.resource_type,
            "amount": row.amount,
            "unit": row.unit,
            "purpose": _loads(row.purpose),
            "actor": row.actor,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
