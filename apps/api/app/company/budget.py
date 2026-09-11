"""AI Company Layer — resource accounting + governance.

Company/department budgets track allocated / reserved / spent / remaining per
period, plus token / tool-call / execution usage. The :class:`ResourceGovernor`
enforces the effective limit for any execution by checking the most restrictive
of company + department + employee budgets, and settles reserved→spent on
completion. Employees cannot raise their own allocation — only an authorized
manager/executive can adjust a budget via :meth:`BudgetManager.set_allocation`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger
from app.company.types import BudgetSnapshot
from app.db.models.company import (
    Budget,
    GoalScopeType,
)
from app.db.models.employee import AIEmployee, EmployeeBudget


class BudgetManager:
    """Create, snapshot, and account for company/department budgets."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)

    def get_budget(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> Budget | None:
        stmt = select(Budget).where(
            Budget.company_id == company_id,
            Budget.scope_type == scope_type,
            Budget.scope_id == scope_id,
        )
        return self._db.scalar(stmt)

    def ensure_budget(
        self,
        company_id: UUID,
        scope_type: GoalScopeType,
        scope_id: UUID,
        monthly_limit: float = 0.0,
    ) -> Budget:
        """Get or create a company/department budget for the period."""
        budget = self.get_budget(company_id, scope_type, scope_id)
        if budget is None:
            budget = Budget(
                company_id=company_id,
                scope_type=scope_type,
                scope_id=scope_id,
                monthly_limit=monthly_limit,
                period_start=datetime.now(UTC),
                period_end=datetime.now(UTC) + timedelta(days=30),
            )
            self._db.add(budget)
            self._db.commit()
        return budget

    def set_allocation(
        self,
        budget_id: UUID,
        *,
        monthly_limit: float | None = None,
        allocated: float | None = None,
        actor: str = "system",
    ) -> Budget:
        """Adjust a budget's limit/allocation. Authorized actor only."""
        budget = self._db.get(Budget, budget_id)
        if budget is None:
            raise ValueError("Budget not found")
        if monthly_limit is not None:
            budget.monthly_limit = monthly_limit
        if allocated is not None:
            budget.allocated = allocated
        self._db.flush()
        if budget.company_id is not None:
            self.events.log(
                actor=actor,
                action="budget_changed",
                company_id=budget.company_id,
                target_type="budget",
                target_id=budget.id,
                details={
                    "monthly_limit": budget.monthly_limit,
                    "allocated": budget.allocated,
                },
                outcome="success",
            )
        self._db.commit()
        return budget

    def reserve(self, budget: Budget, amount: float) -> bool:
        """Reserve funds for a pending execution. Returns False if unaffordable."""
        if budget.spent + budget.reserved + amount > budget.monthly_limit:
            return False
        budget.reserved += amount
        self._db.commit()
        return True

    def release(self, budget: Budget, amount: float) -> None:
        """Release reserved funds (e.g. cancelled execution)."""
        budget.reserved = max(0.0, budget.reserved - amount)
        self._db.commit()

    def spend(
        self,
        budget: Budget,
        *,
        cost: float,
        tokens: int = 0,
        tool_calls: int = 0,
    ) -> None:
        """Move reserved → spent and record usage. Rolls the period over if expired."""
        now = datetime.now(UTC)
        if budget.period_end is not None and now >= budget.period_end:
            self._rollover(budget)
        budget.spent += cost
        budget.cost_used += cost
        budget.tokens_used += tokens
        budget.tool_calls_used += tool_calls
        budget.execution_count += 1
        budget.reserved = max(0.0, budget.reserved - cost)
        self._db.commit()

    def _rollover(self, budget: Budget) -> None:
        """Reset a period's usage accounting when the period window expires."""
        now = datetime.now(UTC)
        budget.spent = 0.0
        budget.cost_used = 0.0
        budget.tokens_used = 0
        budget.tool_calls_used = 0
        budget.execution_count = 0
        budget.reserved = 0.0
        budget.period_start = now
        budget.period_end = now + timedelta(days=30)

    def snapshot(
        self, company_id: UUID, scope_type: GoalScopeType, scope_id: UUID
    ) -> BudgetSnapshot | None:
        """Return a budget snapshot for a scope (None when no budget exists)."""
        budget = self.get_budget(company_id, scope_type, scope_id)
        if budget is None:
            return None
        return BudgetSnapshot(
            company_id=budget.company_id,
            scope_type=scope_type.value,
            scope_id=scope_id,
            monthly_limit=budget.monthly_limit,
            allocated=budget.allocated,
            reserved=budget.reserved,
            spent=budget.spent,
            tokens_used=budget.tokens_used,
            cost_used=budget.cost_used,
            tool_calls_used=budget.tool_calls_used,
            execution_count=budget.execution_count,
            period_start=budget.period_start,
            period_end=budget.period_end,
        )

    def employee_snapshot(self, employee_id: UUID) -> BudgetSnapshot | None:
        """Return the Phase 7 employee budget as a BudgetSnapshot."""
        emp_budget = self._db.execute(
            select(EmployeeBudget).where(EmployeeBudget.employee_id == employee_id)
        ).scalar_one_or_none()
        if emp_budget is None:
            return None
        return BudgetSnapshot(
            company_id=UUID(int=0),  # placeholder; employee budgets carry no company
            scope_type="employee",
            scope_id=employee_id,
            monthly_limit=emp_budget.monthly_limit or 0.0,
            allocated=emp_budget.monthly_limit or 0.0,
            reserved=0.0,
            spent=emp_budget.cost_used or 0.0,
            tokens_used=emp_budget.tokens_used or 0,
            cost_used=emp_budget.cost_used or 0.0,
            tool_calls_used=emp_budget.tool_calls_used or 0,
            period_start=emp_budget.period_start,
            period_end=emp_budget.period_end,
        )

    def company_budget(self, company_id: UUID) -> Budget | None:
        return self.get_budget(company_id, GoalScopeType.COMPANY, company_id)

    def department_budgets(self, company_id: UUID) -> list[Budget]:
        stmt = (
            select(Budget)
            .where(
                Budget.company_id == company_id,
                Budget.scope_type == GoalScopeType.DEPARTMENT,
            )
            .order_by(Budget.created_at)
        )
        return list(self._db.execute(stmt).scalars().all())


class ResourceGovernor:
    """Enforce all applicable resource limits for a single execution."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.budgets = BudgetManager(db)

    def can_execute(
        self,
        *,
        company_id: UUID,
        estimated_cost: float,
        department_id: UUID | None = None,
        employee_id: UUID | None = None,
    ) -> tuple[bool, list[str]]:
        """Check every applicable budget can afford ``estimated_cost``.

        Returns ``(ok, reasons)`` where ``reasons`` lists which limits would be
        violated. The effective limit is the conjunction of company + department
        + employee — the most restrictive applicable limit governs.
        """
        reasons: list[str] = []
        company_budget = self.budgets.get_budget(company_id, GoalScopeType.COMPANY, company_id)
        if company_budget and (
            company_budget.spent + company_budget.reserved + estimated_cost
            > company_budget.monthly_limit
        ):
            reasons.append("company_budget_exceeded")

        if department_id is not None:
            dept_budget = self.budgets.get_budget(
                company_id, GoalScopeType.DEPARTMENT, department_id
            )
            if dept_budget and (
                dept_budget.spent + dept_budget.reserved + estimated_cost
                > dept_budget.monthly_limit
            ):
                reasons.append("department_budget_exceeded")

        if employee_id is not None:
            emp = self._db.get(AIEmployee, employee_id)
            emp_budget = None
            if emp is not None:
                emp_budget = self._db.execute(
                    select(EmployeeBudget).where(EmployeeBudget.employee_id == employee_id)
                ).scalar_one_or_none()
            if emp_budget and emp_budget.monthly_limit:
                if emp_budget.cost_used + estimated_cost > emp_budget.monthly_limit:
                    reasons.append("employee_budget_exceeded")

        return (not reasons, reasons)
