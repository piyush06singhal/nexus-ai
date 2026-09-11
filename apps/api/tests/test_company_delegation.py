"""Tests for AI Company Layer — work delegation with authorization."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.company.delegation import DelegationService
from app.company.membership import MembershipManager
from app.company.roles import RoleManager
from app.db.models.agent import Agent
from app.db.models.company import AuthorityLevel
from app.db.models.employee import AIEmployee, EmployeeStatus


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


def _make_employee(db: Session, name: str):
    agent = Agent(name=f"{name}-agent", model_name="test")
    db.add(agent)
    db.flush()
    emp = AIEmployee(
        name=name.lower(),
        display_name=name,
        role="engineer",
        status=EmployeeStatus.ACTIVE,
        skills="python",
        agent_id=agent.id,
    )
    db.add(emp)
    db.commit()
    return emp


class TestDelegation:
    def test_can_delegate_manager_to_report(self, db: Session) -> None:
        company = _make_company(db)
        boss = _make_employee(db, "Boss")
        emp = _make_employee(db, "Emp")
        role = RoleManager(db).create(
            company_id=company.id,
            name="mgr",
            title="Manager",
            authority_level=AuthorityLevel.MANAGER,
        )
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=boss.id, role_id=role.id)
        mm.add(
            company_id=company.id,
            employee_id=emp.id,
            manager_id=boss.id,
        )
        svc = DelegationService(db)
        ok, reasons = svc.can_delegate(
            company_id=company.id,
            from_employee_id=boss.id,
            to_employee_id=emp.id,
        )
        assert ok is True
        assert reasons == []

    def test_cannot_delegate_ic(self, db: Session) -> None:
        company = _make_company(db)
        ic = _make_employee(db, "IC")
        emp = _make_employee(db, "Emp")
        role = RoleManager(db).create(
            company_id=company.id,
            name="ic",
            title="IC",
            authority_level=AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        )
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=ic.id, role_id=role.id)
        mm.add(
            company_id=company.id,
            employee_id=emp.id,
            manager_id=ic.id,
        )
        svc = DelegationService(db)
        ok, reasons = svc.can_delegate(
            company_id=company.id,
            from_employee_id=ic.id,
            to_employee_id=emp.id,
        )
        assert ok is False
        assert "insufficient_authority" in reasons

    def test_cannot_delegate_to_non_report(self, db: Session) -> None:
        company = _make_company(db)
        boss = _make_employee(db, "Boss")
        emp = _make_employee(db, "Emp")
        role = RoleManager(db).create(
            company_id=company.id,
            name="mgr",
            title="Manager",
            authority_level=AuthorityLevel.MANAGER,
        )
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=boss.id, role_id=role.id)
        mm.add(company_id=company.id, employee_id=emp.id)  # No manager set
        svc = DelegationService(db)
        ok, reasons = svc.can_delegate(
            company_id=company.id,
            from_employee_id=boss.id,
            to_employee_id=emp.id,
        )
        assert ok is False
        assert "to_not_direct_report" in reasons

    def test_delegate_success(self, db: Session) -> None:
        company = _make_company(db)
        boss = _make_employee(db, "Boss")
        emp = _make_employee(db, "Emp")
        role = RoleManager(db).create(
            company_id=company.id,
            name="mgr",
            title="Manager",
            authority_level=AuthorityLevel.MANAGER,
        )
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=boss.id, role_id=role.id)
        mm.add(
            company_id=company.id,
            employee_id=emp.id,
            manager_id=boss.id,
        )
        svc = DelegationService(db)
        result = svc.delegate(
            company_id=company.id,
            from_employee_id=boss.id,
            to_employee_id=emp.id,
            task_name="Review code",
            task_description="Review PR #42",
        )
        assert result["delegated"] is True
        assert result["task_name"] == "Review code"

    def test_delegate_denied_records_event(self, db: Session) -> None:
        company = _make_company(db)
        emp1 = _make_employee(db, "A")
        emp2 = _make_employee(db, "B")
        mm = MembershipManager(db)
        mm.add(company_id=company.id, employee_id=emp1.id)
        mm.add(company_id=company.id, employee_id=emp2.id)
        svc = DelegationService(db)
        result = svc.delegate(
            company_id=company.id,
            from_employee_id=emp1.id,
            to_employee_id=emp2.id,
            task_name="Do work",
        )
        assert result["delegated"] is False
        assert len(result["reasons"]) > 0
