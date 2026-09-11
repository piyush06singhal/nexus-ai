"""AI Company Layer — data-driven organization chart builder.

Assembles the org chart tree from departments and memberships (no hardcoded
departments or roles). The tree is bounded: descendant traversal is iterative
and builds exactly the company's departments + members, so it never loads an
entire company into memory or recurses unboundedly.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.types import OrgChart, OrgChartNode
from app.db.models.company import (
    Department,
    OrganizationalMembership,
)
from app.db.models.employee import AIEmployee


class OrgChartBuilder:
    """Build the organization chart for a company."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def build(self, company_id: UUID, company_name: str) -> OrgChart:
        """Build the org chart rooted at the company."""
        departments = list(
            self._db.execute(
                select(Department)
                .where(Department.company_id == company_id)
                .order_by(Department.name)
            ).scalars()
        )
        memberships = list(
            self._db.execute(
                select(OrganizationalMembership).where(
                    OrganizationalMembership.company_id == company_id
                )
            ).scalars()
        )
        employees = self._employee_map([m.employee_id for m in memberships])

        root = OrgChartNode(id=company_id, type="company", name=company_name)

        # Department tree: id -> [child dept ids]
        dept_children: dict[UUID, list[Department]] = defaultdict(list)
        root_departments: list[Department] = []
        for d in departments:
            if d.parent_department_id is not None:
                dept_children[d.parent_department_id].append(d)
            else:
                root_departments.append(d)

        # Employee nodes under each department (top-level dept or company root)
        dept_employee_nodes: dict[UUID, list[OrgChartNode]] = defaultdict(list)
        top_employee_nodes: list[OrgChartNode] = []
        for m in memberships:
            node = OrgChartNode(
                id=m.employee_id,
                type="employee",
                name=(employees.get(m.employee_id) or "Unknown"),
                status=self._employee_status(m.employee_id),
                manager_id=m.manager_id,
            )
            if m.department_id is not None:
                dept_employee_nodes[m.department_id].append(node)
            else:
                top_employee_nodes.append(node)

        managers: set[UUID] = {m.manager_id for m in memberships if m.manager_id}

        def _build_department_node(dept: Department) -> OrgChartNode:
            node = OrgChartNode(
                id=dept.id,
                type="department",
                name=dept.name,
                role="department",
                status=dept.status.value if dept.status else None,
                manager_id=dept.manager_id,
            )
            for child_dept in dept_children.get(dept.id, []):
                node.children.append(_build_department_node(child_dept))
            node.children.extend(sorted(dept_employee_nodes.get(dept.id, []), key=lambda n: n.name))
            return node

        for dept in root_departments:
            root.children.append(_build_department_node(dept))
        root.children.extend(sorted(top_employee_nodes, key=lambda n: n.name))

        return OrgChart(
            company_id=company_id,
            company_name=company_name,
            root=root,
            departments=len(departments),
            employees=len(memberships),
            managers=len(managers),
        )

    def _employee_map(self, employee_ids: list[UUID]) -> dict[UUID, str]:
        if not employee_ids:
            return {}
        stmt = select(AIEmployee).where(AIEmployee.id.in_(employee_ids))
        return {e.id: (e.display_name or e.name) for e in self._db.execute(stmt).scalars()}

    def _employee_status(self, employee_id: UUID) -> str | None:
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return None
        status_val = emp.status
        return getattr(status_val, "value", str(status_val))
