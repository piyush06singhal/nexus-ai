"""Tests for AI Company Layer — budgets, resource governance, and enforcement."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.company.budget import BudgetManager, ResourceGovernor
from app.db.models.company import GoalScopeType


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


def _make_dept(db: Session, company_id):
    from app.company.departments import DepartmentManager

    return DepartmentManager(db).create(company_id=company_id, name="Engineering")


class TestBudgetCRUD:
    def test_ensure_creates_budget(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        budget = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 10000.0)
        assert budget.monthly_limit == 10000.0
        assert budget.spent == 0.0

    def test_ensure_idempotent(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        b1 = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 10000.0)
        b2 = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 10000.0)
        assert b1.id == b2.id

    def test_set_allocation(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        budget = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 10000.0)
        updated = mgr.set_allocation(budget.id, monthly_limit=20000.0, allocated=5000.0)
        assert updated.monthly_limit == 20000.0
        assert updated.allocated == 5000.0


class TestBudgetAccounting:
    def test_reserve(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        budget = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        assert mgr.reserve(budget, 30.0) is True
        assert budget.reserved == 30.0

    def test_reserve_exceeds_limit(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        budget = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        assert mgr.reserve(budget, 150.0) is False
        assert budget.reserved == 0.0

    def test_spend(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        budget = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        mgr.reserve(budget, 50.0)
        mgr.spend(budget, cost=30.0, tokens=1000, tool_calls=5)
        assert budget.spent == 30.0
        assert budget.tokens_used == 1000
        assert budget.tool_calls_used == 5
        assert budget.execution_count == 1
        assert budget.reserved == 20.0  # 50 reserved - 30 spent

    def test_release(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        budget = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        mgr.reserve(budget, 50.0)
        mgr.release(budget, 20.0)
        assert budget.reserved == 30.0

    def test_snapshot(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        budget = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        mgr.spend(budget, cost=25.0)
        snap = mgr.snapshot(company.id, GoalScopeType.COMPANY, company.id)
        assert snap is not None
        assert snap.spent == 25.0
        assert snap.monthly_limit == 100.0

    def test_snapshot_none_when_no_budget(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        snap = mgr.snapshot(company.id, GoalScopeType.COMPANY, company.id)
        assert snap is None

    def test_department_budgets(self, db: Session) -> None:
        company = _make_company(db)
        dept = _make_dept(db, company.id)
        mgr = BudgetManager(db)
        mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 10000.0)
        mgr.ensure_budget(company.id, GoalScopeType.DEPARTMENT, dept.id, 5000.0)
        dept_budgets = mgr.department_budgets(company.id)
        assert len(dept_budgets) == 1


class TestResourceGovernor:
    def test_can_execute_within_budget(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        gov = ResourceGovernor(db)
        ok, reasons = gov.can_execute(company_id=company.id, estimated_cost=50.0)
        assert ok is True
        assert reasons == []

    def test_can_execute_over_budget(self, db: Session) -> None:
        company = _make_company(db)
        mgr = BudgetManager(db)
        budget = mgr.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        mgr.spend(budget, cost=90.0)
        gov = ResourceGovernor(db)
        ok, reasons = gov.can_execute(company_id=company.id, estimated_cost=20.0)
        assert ok is False
        assert "company_budget_exceeded" in reasons

    def test_department_budget_exceeded(self, db: Session) -> None:
        company = _make_company(db)
        dept = _make_dept(db, company.id)
        mgr = BudgetManager(db)
        budget = mgr.ensure_budget(company.id, GoalScopeType.DEPARTMENT, dept.id, 100.0)
        mgr.spend(budget, cost=90.0)
        gov = ResourceGovernor(db)
        ok, reasons = gov.can_execute(
            company_id=company.id,
            estimated_cost=20.0,
            department_id=dept.id,
        )
        assert ok is False
        assert "department_budget_exceeded" in reasons
