"""Tests for AI Company Layer — decisions lifecycle and authorization."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.company.decisions import DecisionManager
from app.company.lifecycle import CompanyLifecycleError
from app.db.models.company import (
    AuthorityLevel,
    DecisionStatus,
)


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


def _make_employee(db: Session, name: str = "Alice"):
    from app.db.models.agent import Agent
    from app.db.models.employee import AIEmployee, EmployeeStatus

    agent = Agent(name=f"{name}-agent", model_name="test")
    db.add(agent)
    db.flush()
    emp = AIEmployee(
        name=name.lower(),
        display_name=name,
        role="manager",
        status=EmployeeStatus.ACTIVE,
        skills="python",
        agent_id=agent.id,
    )
    db.add(emp)
    db.commit()
    return emp


def _make_executive(db: Session, company_id):
    """Create an employee with executive-level role membership."""
    from app.company.membership import MembershipManager
    from app.company.roles import RoleManager

    emp = _make_employee(db, "Executive")
    role = RoleManager(db).create(
        company_id=company_id,
        name="exec",
        title="Executive",
        authority_level=AuthorityLevel.EXECUTIVE,
    )
    MembershipManager(db).add(
        company_id=company_id,
        employee_id=emp.id,
        role_id=role.id,
    )
    return emp


class TestDecisionCRUD:
    def test_create_decision(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DecisionManager(db)
        decision = mgr.create(
            company_id=company.id,
            question="Should we use Python?",
            options=[{"name": "Python"}, {"name": "Go"}],
        )
        assert decision.status == DecisionStatus.DRAFT
        assert decision.question == "Should we use Python?"

    def test_list_decisions(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DecisionManager(db)
        mgr.create(
            company_id=company.id,
            question="Q1",
            options=[{"name": "A"}],
        )
        mgr.create(
            company_id=company.id,
            question="Q2",
            options=[{"name": "B"}],
        )
        decisions = mgr.list_(company.id)
        assert len(decisions) == 2


class TestDecisionLifecycle:
    def test_submit(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DecisionManager(db)
        d = mgr.create(
            company_id=company.id,
            question="Q",
            options=[{"name": "A"}],
        )
        submitted = mgr.submit(d.id)
        assert submitted.status == DecisionStatus.PENDING_REVIEW

    def test_approve(self, db: Session) -> None:
        company = _make_company(db)
        exec_emp = _make_executive(db, company.id)
        mgr = DecisionManager(db)
        d = mgr.create(
            company_id=company.id,
            question="Q",
            options=[{"name": "A"}],
        )
        mgr.submit(d.id)
        approved = mgr.approve(d.id, reviewer_id=exec_emp.id, rationale="Looks good")
        assert approved.status == DecisionStatus.APPROVED
        assert approved.decision_maker_id == exec_emp.id

    def test_reject(self, db: Session) -> None:
        company = _make_company(db)
        exec_emp = _make_executive(db, company.id)
        mgr = DecisionManager(db)
        d = mgr.create(
            company_id=company.id,
            question="Q",
            options=[{"name": "A"}],
        )
        mgr.submit(d.id)
        rejected = mgr.reject(d.id, reviewer_id=exec_emp.id, rationale="No")
        assert rejected.status == DecisionStatus.REJECTED

    def test_implement(self, db: Session) -> None:
        company = _make_company(db)
        exec_emp = _make_executive(db, company.id)
        mgr = DecisionManager(db)
        d = mgr.create(
            company_id=company.id,
            question="Q",
            options=[{"name": "A"}],
        )
        mgr.submit(d.id)
        mgr.approve(d.id, reviewer_id=exec_emp.id, rationale="OK")
        impl = mgr.implement(d.id, actor_id=exec_emp.id)
        assert impl.status == DecisionStatus.IMPLEMENTED

    def test_cannot_approve_draft(self, db: Session) -> None:
        company = _make_company(db)
        exec_emp = _make_executive(db, company.id)
        mgr = DecisionManager(db)
        d = mgr.create(
            company_id=company.id,
            question="Q",
            options=[{"name": "A"}],
        )
        with pytest.raises(CompanyLifecycleError):
            mgr.approve(d.id, reviewer_id=exec_emp.id, rationale="skip review")

    def test_cannot_approve_without_authority(self, db: Session) -> None:
        company = _make_company(db)
        # Create a regular IC employee
        from app.company.membership import MembershipManager
        from app.company.roles import RoleManager

        emp = _make_employee(db, "IC")
        role = RoleManager(db).create(
            company_id=company.id,
            name="ic",
            title="IC",
            authority_level=AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        )
        MembershipManager(db).add(
            company_id=company.id,
            employee_id=emp.id,
            role_id=role.id,
        )
        mgr = DecisionManager(db)
        d = mgr.create(
            company_id=company.id,
            question="Q",
            options=[{"name": "A"}],
            required_authority=AuthorityLevel.EXECUTIVE,
        )
        mgr.submit(d.id)
        with pytest.raises(CompanyLifecycleError, match="authority"):
            mgr.approve(d.id, reviewer_id=emp.id, rationale="Try")

    def test_reviews_audit_trail(self, db: Session) -> None:
        company = _make_company(db)
        exec_emp = _make_executive(db, company.id)
        mgr = DecisionManager(db)
        d = mgr.create(
            company_id=company.id,
            question="Q",
            options=[{"name": "A"}],
        )
        mgr.submit(d.id)
        mgr.approve(d.id, reviewer_id=exec_emp.id, rationale="OK")
        reviews = mgr.reviews(d.id)
        assert len(reviews) >= 3  # created + submitted + approved

    def test_to_dict(self, db: Session) -> None:
        company = _make_company(db)
        mgr = DecisionManager(db)
        d = mgr.create(
            company_id=company.id,
            question="Should we use Python?",
            options=[{"name": "Python"}, {"name": "Go"}],
        )
        dd = mgr.to_dict(d)
        assert dd["question"] == "Should we use Python?"
        assert len(dd["options"]) == 2
        assert dd["status"] == "draft"
