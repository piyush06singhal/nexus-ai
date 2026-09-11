"""Tests for AI Company Layer — department CRUD, hierarchy, lifecycle, and membership."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.company.departments import DepartmentManager
from app.company.lifecycle import CompanyLifecycleError
from app.company.membership import MembershipManager
from app.db.models.company import (
    Company,
    DepartmentStatus,
)
from app.db.models.employee import AIEmployee, EmployeeStatus

# ── Fixtures ──────────────────────────────────────────────────────────────────


_company_counter = 0


def _make_company(db: Session, name: str | None = None) -> Company:
    from app.company.manager import CompanyManager

    global _company_counter
    _company_counter += 1
    mgr = CompanyManager(db)
    return mgr.create(name=name or f"Test Co {_company_counter}", industry="tech")


def _make_employee(db: Session, name: str = "Alice") -> AIEmployee:
    emp = AIEmployee(
        name=name.lower(),
        display_name=name,
        role="engineer",
        status=EmployeeStatus.ACTIVE,
        skills="python,testing",
    )
    db.add(emp)
    db.commit()
    return emp


# ── Department CRUD ───────────────────────────────────────────────────────────


class TestDepartmentCRUD:
    def test_create_department(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        assert dept.name == "Engineering"
        assert dept.company_id == company.id
        assert dept.status == DepartmentStatus.DRAFT

    def test_get_department(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        found = mgr.get(dept.id)
        assert found is not None
        assert found.id == dept.id

    def test_list_departments(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        mgr.create(company_id=company.id, name="Engineering")
        mgr.create(company_id=company.id, name="Marketing")
        depts = mgr.list_(company.id)
        assert len(depts) == 2
        names = {d.name for d in depts}
        assert "Engineering" in names
        assert "Marketing" in names

    def test_update_department(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        updated = mgr.update(dept.id, description="Builds things")
        assert updated.description == "Builds things"

    def test_update_archived_is_readonly(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        mgr.activate(dept.id)
        mgr.archive(dept.id)
        with pytest.raises(CompanyLifecycleError):
            mgr.update(dept.id, description="Nope")


# ── Hierarchy ─────────────────────────────────────────────────────────────────


class TestDepartmentHierarchy:
    def test_nested_department(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        parent = mgr.create(company_id=company.id, name="Engineering")
        child = mgr.create(
            company_id=company.id,
            name="Backend",
            parent_department_id=parent.id,
        )
        assert child.parent_department_id == parent.id

    def test_parent_must_belong_to_same_company(self, db: Session) -> None:
        company1 = _make_company(db)
        company2 = _make_company(db)
        mgr = DepartmentManager(db)
        dept1 = mgr.create(company_id=company1.id, name="Dept1")
        with pytest.raises(ValueError, match="Parent department not found or belongs to another"):
            mgr.create(
                company_id=company2.id,
                name="Dept2",
                parent_department_id=dept1.id,
            )

    def test_children(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        parent = mgr.create(company_id=company.id, name="Engineering")
        mgr.create(company_id=company.id, name="Frontend", parent_department_id=parent.id)
        mgr.create(company_id=company.id, name="Backend", parent_department_id=parent.id)
        kids = mgr.children(parent.id)
        assert len(kids) == 2

    def test_subtree_ids(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        root = mgr.create(company_id=company.id, name="Root")
        child = mgr.create(company_id=company.id, name="Child", parent_department_id=root.id)
        grandchild = mgr.create(
            company_id=company.id, name="Grandchild", parent_department_id=child.id
        )
        ids = mgr.subtree_ids(root.id)
        assert root.id in ids
        assert child.id in ids
        assert grandchild.id in ids
        assert len(ids) == 3


# ── Department lifecycle ──────────────────────────────────────────────────────


class TestDepartmentLifecycle:
    def test_activate(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        activated = mgr.activate(dept.id)
        assert activated.status == DepartmentStatus.ACTIVE

    def test_pause_from_active(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        mgr.activate(dept.id)
        paused = mgr.pause(dept.id)
        assert paused.status == DepartmentStatus.PAUSED

    def test_archive(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        mgr.activate(dept.id)
        archived = mgr.archive(dept.id)
        assert archived.status == DepartmentStatus.ARCHIVED

    def test_invalid_transition_draft_to_paused(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        with pytest.raises(CompanyLifecycleError):
            mgr.pause(dept.id)

    def test_invalid_transition_archived(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        mgr.activate(dept.id)
        mgr.archive(dept.id)
        with pytest.raises(CompanyLifecycleError):
            mgr.activate(dept.id)


# ── Department employees via membership ───────────────────────────────────────


class TestDepartmentEmployees:
    def test_employees_in_department(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee(db, "Alice")
        mgr = DepartmentManager(db)
        dept = mgr.create(company_id=company.id, name="Engineering")
        MembershipManager(db).add(company_id=company.id, employee_id=emp.id, department_id=dept.id)
        emps = mgr.employees(dept.id)
        assert len(emps) == 1
        assert emps[0].id == emp.id

    def test_employees_in_subtree(self, db: Session) -> None:
        company = _make_company(db)
        emp1 = _make_employee(db, "Alice")
        emp2 = _make_employee(db, "Bob")
        dept_mgr = DepartmentManager(db)
        parent = dept_mgr.create(company_id=company.id, name="Engineering")
        child = dept_mgr.create(
            company_id=company.id, name="Backend", parent_department_id=parent.id
        )
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=emp1.id, department_id=parent.id)
        mm.add(company_id=company.id, employee_id=emp2.id, department_id=child.id)
        emps = dept_mgr.employees(parent.id, include_subtree=True)
        assert len(emps) == 2
