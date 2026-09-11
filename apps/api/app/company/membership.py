"""AI Company Layer — organizational membership service.

Extends Phase 7 employees into the organizational hierarchy without a second
employee model. A membership ties an existing :class:`AIEmployee` to a company,
department, role, and manager, enabling the reporting tree (manager → direct
reports → peers), department membership, and the data-driven organization chart.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger
from app.company.roles import RoleManager
from app.db.models.company import (
    OrganizationalMembership,
    OrganizationalRole,
)
from app.db.models.employee import AIEmployee


class MembershipManager:
    """Add, update, query, and remove employee organizational memberships."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)
        self.roles = RoleManager(db)

    def add(
        self,
        *,
        company_id: UUID,
        employee_id: UUID,
        department_id: UUID | None = None,
        role_id: UUID | None = None,
        responsibility: str = "ic",
        manager_id: UUID | None = None,
    ) -> OrganizationalMembership:
        """Add an employee to a company (one active membership per employee)."""
        existing = self.get(company_id, employee_id)
        if existing is not None:
            raise ValueError("Employee already belongs to this company")
        employee = self._db.get(AIEmployee, employee_id)
        if employee is None:
            raise ValueError("Employee not found")
        if manager_id is not None and self.get(company_id, manager_id) is None:
            raise ValueError("Manager is not a member of this company")

        membership = OrganizationalMembership(
            company_id=company_id,
            employee_id=employee_id,
            department_id=department_id,
            role_id=role_id,
            responsibility=responsibility,
            manager_id=manager_id,
        )
        self._db.add(membership)
        self._db.flush()
        self.events.log(
            actor="system",
            action="employee_added",
            company_id=company_id,
            target_type="employee",
            target_id=employee_id,
            details={
                "department_id": str(department_id) if department_id else None,
                "responsibility": responsibility,
                "manager_id": str(manager_id) if manager_id else None,
            },
            outcome="success",
        )
        self._db.commit()
        return membership

    def get(self, company_id: UUID, employee_id: UUID) -> OrganizationalMembership | None:
        stmt = select(OrganizationalMembership).where(
            OrganizationalMembership.company_id == company_id,
            OrganizationalMembership.employee_id == employee_id,
        )
        return self._db.scalar(stmt)

    def _require(self, membership_id: UUID) -> OrganizationalMembership:
        mem = self._db.get(OrganizationalMembership, membership_id)
        if mem is None:
            raise ValueError("Membership not found")
        return mem

    def update(
        self,
        membership_id: UUID,
        *,
        department_id: UUID | None = None,
        role_id: UUID | None = None,
        responsibility: str | None = None,
        manager_id: UUID | None = None,
    ) -> OrganizationalMembership:
        """Update a membership. Pass a value to change it; pass ``None`` to keep."""
        mem = self._require(membership_id)
        company_id = mem.company_id
        if department_id is not None:
            mem.department_id = department_id
        if role_id is not None:
            mem.role_id = role_id
        if responsibility is not None:
            mem.responsibility = responsibility
        if manager_id is not None:
            if self.get(company_id, manager_id) is None:
                raise ValueError("Manager is not a member of this company")
            mem.manager_id = manager_id
        self._db.flush()
        self.events.log(
            actor="system",
            action="employee_moved",
            company_id=company_id,
            target_type="employee",
            target_id=mem.employee_id,
            details={
                "department_id": str(mem.department_id) if mem.department_id else None,
                "manager_id": str(mem.manager_id) if mem.manager_id else None,
                "responsibility": mem.responsibility,
            },
            outcome="success",
        )
        self._db.commit()
        return mem

    def remove(self, membership_id: UUID) -> bool:
        mem = self._require(membership_id)
        self.events.log(
            actor="system",
            action="employee_removed",
            company_id=mem.company_id,
            target_type="employee",
            target_id=mem.employee_id,
            outcome="success",
        )
        self._db.delete(mem)
        self._db.commit()
        return True

    # ── Listing ────────────────────────────────────────────────────────

    def list(self, company_id: UUID) -> list[OrganizationalMembership]:
        stmt = (
            select(OrganizationalMembership)
            .where(OrganizationalMembership.company_id == company_id)
            .order_by(OrganizationalMembership.created_at)
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_employees(self, company_id: UUID) -> list[AIEmployee]:
        """Return the Phase 7 employees who are members of this company."""
        stmt = (
            select(AIEmployee)
            .join(OrganizationalMembership, OrganizationalMembership.employee_id == AIEmployee.id)
            .where(OrganizationalMembership.company_id == company_id)
            .order_by(AIEmployee.name)
        )
        return list(self._db.execute(stmt).scalars().all())

    def direct_reports(self, company_id: UUID, manager_id: UUID) -> list[OrganizationalMembership]:
        """Return memberships directly reporting to ``manager_id``."""
        stmt = select(OrganizationalMembership).where(
            OrganizationalMembership.company_id == company_id,
            OrganizationalMembership.manager_id == manager_id,
        )
        return list(self._db.execute(stmt).scalars().all())

    def peers(self, company_id: UUID, employee_id: UUID) -> list[OrganizationalMembership]:
        """Return memberships sharing the same manager (excluding self)."""
        mem = self.get(company_id, employee_id)
        if mem is None or mem.manager_id is None:
            return []
        stmt = select(OrganizationalMembership).where(
            OrganizationalMembership.company_id == company_id,
            OrganizationalMembership.manager_id == mem.manager_id,
            OrganizationalMembership.employee_id != employee_id,
        )
        return list(self._db.execute(stmt).scalars().all())

    def get_team(self, company_id: UUID, manager_id: UUID) -> list[AIEmployee]:
        """Return the employees directly reporting to a manager."""
        reports = self.direct_reports(company_id, manager_id)
        ids = [r.employee_id for r in reports]
        if not ids:
            return []
        stmt = select(AIEmployee).where(AIEmployee.id.in_(ids)).order_by(AIEmployee.name)
        return list(self._db.execute(stmt).scalars().all())

    def role_of(self, membership: OrganizationalMembership) -> OrganizationalRole | None:
        if membership.role_id is None:
            return None
        return self._db.get(OrganizationalRole, membership.role_id)

    def to_dict(self, mem: OrganizationalMembership) -> dict[str, Any]:
        """Serialize a membership with employee + role context for APIs."""
        role = self.role_of(mem)
        employee = self._db.get(AIEmployee, mem.employee_id)
        return {
            "id": str(mem.id),
            "company_id": str(mem.company_id),
            "employee_id": str(mem.employee_id),
            "employee_name": employee.display_name or employee.name if employee else None,
            "role": employee.role if employee else None,
            "department_id": str(mem.department_id) if mem.department_id else None,
            "role_id": str(mem.role_id) if mem.role_id else None,
            "role_title": role.title if role else None,
            "authority_level": role.authority_level.value if role else None,
            "responsibility": mem.responsibility,
            "manager_id": str(mem.manager_id) if mem.manager_id else None,
            "created_at": mem.created_at.isoformat() if mem.created_at else None,
            "updated_at": mem.updated_at.isoformat() if mem.updated_at else None,
        }
