"""Tests for AI Company Layer — membership, reporting tree, and org chart."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.company.membership import MembershipManager
from app.db.models.agent import Agent
from app.db.models.company import (
    AuthorityLevel,
    Company,
)
from app.db.models.employee import AIEmployee, EmployeeStatus


def _make_company(db: Session) -> Company:
    from app.company.manager import CompanyManager

    mgr = CompanyManager(db)
    return mgr.create(name="Test Co", industry="tech")


def _make_employee(db: Session, name: str = "Alice") -> AIEmployee:
    agent = Agent(name=f"{name}-agent", model_name="test")
    db.add(agent)
    db.flush()
    emp = AIEmployee(
        name=name.lower(),
        display_name=name,
        role="engineer",
        status=EmployeeStatus.ACTIVE,
        skills="python,testing",
        agent_id=agent.id,
    )
    db.add(emp)
    db.commit()
    return emp


def _make_role(
    db: Session,
    company_id,
    name: str = "Engineer",
    level: AuthorityLevel = AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
):
    from app.company.roles import RoleManager

    mgr = RoleManager(db)
    return mgr.create(company_id=company_id, name=name, title=name, authority_level=level)


# ── Membership CRUD ───────────────────────────────────────────────────────────


class TestMembershipCRUD:
    def test_add_membership(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee(db)
        mm = MembershipManager(db)
        mem = mm.add(company_id=company.id, employee_id=emp.id)
        assert mem.company_id == company.id
        assert mem.employee_id == emp.id

    def test_duplicate_membership_raises(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee(db)
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=emp.id)
        with pytest.raises(ValueError, match="already belongs"):
            mm.add(company_id=company.id, employee_id=emp.id)

    def test_employee_not_found(self, db: Session) -> None:
        company = _make_company(db)
        mm = MembershipManager(db)
        with pytest.raises(ValueError, match="Employee not found"):
            mm.add(company_id=company.id, employee_id=uuid4())

    def test_remove_membership(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee(db)
        mm = MembershipManager(db)
        mem = mm.add(company_id=company.id, employee_id=emp.id)
        assert mm.remove(mem.id) is True
        assert mm.get(company.id, emp.id) is None

    def test_update_membership(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee(db)
        mm = MembershipManager(db)
        mem = mm.add(company_id=company.id, employee_id=emp.id)
        dept_id = uuid4()
        updated = mm.update(mem.id, department_id=dept_id)
        assert updated.department_id == dept_id


# ── Reporting tree ────────────────────────────────────────────────────────────


class TestReportingTree:
    def test_direct_reports(self, db: Session) -> None:
        company = _make_company(db)
        boss = _make_employee(db, "Boss")
        emp1 = _make_employee(db, "Emp1")
        emp2 = _make_employee(db, "Emp2")
        mm = MembershipManager(db)
        mm.add(
            company_id=company.id,
            employee_id=boss.id,
            responsibility="manager",
        )
        mm.add(
            company_id=company.id,
            employee_id=emp1.id,
            manager_id=boss.id,
        )
        mm.add(
            company_id=company.id,
            employee_id=emp2.id,
            manager_id=boss.id,
        )
        reports = mm.direct_reports(company.id, boss.id)
        assert len(reports) == 2

    def test_peers(self, db: Session) -> None:
        company = _make_company(db)
        boss = _make_employee(db, "Boss")
        emp1 = _make_employee(db, "Emp1")
        emp2 = _make_employee(db, "Emp2")
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=boss.id, responsibility="manager")
        mm.add(company_id=company.id, employee_id=emp1.id, manager_id=boss.id)
        mm.add(company_id=company.id, employee_id=emp2.id, manager_id=boss.id)
        peers = mm.peers(company.id, emp1.id)
        assert len(peers) == 1
        assert peers[0].employee_id == emp2.id

    def test_peers_no_manager(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee(db)
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=emp.id)
        assert mm.peers(company.id, emp.id) == []

    def test_get_team(self, db: Session) -> None:
        company = _make_company(db)
        boss = _make_employee(db, "Boss")
        emp = _make_employee(db, "Emp")
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=boss.id, responsibility="manager")
        mm.add(company_id=company.id, employee_id=emp.id, manager_id=boss.id)
        team = mm.get_team(company.id, boss.id)
        assert len(team) == 1
        assert team[0].id == emp.id

    def test_manager_not_in_company(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee(db)
        mm = MembershipManager(db)
        with pytest.raises(ValueError, match="Manager is not a member"):
            mm.add(
                company_id=company.id,
                employee_id=emp.id,
                manager_id=uuid4(),
            )


# ── to_dict ───────────────────────────────────────────────────────────────────


class TestMembershipSerialization:
    def test_to_dict(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee(db, "Alice")
        role = _make_role(db, company.id)
        mm = MembershipManager(db)
        mem = mm.add(
            company_id=company.id,
            employee_id=emp.id,
            role_id=role.id,
        )
        d = mm.to_dict(mem)
        assert d["employee_name"] == "Alice"
        assert d["role_title"] == "Engineer"
        assert d["authority_level"] == "individual_contributor"
