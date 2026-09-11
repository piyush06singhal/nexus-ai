"""Tests for AI Company Layer — analytics and forecasting."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.company.analytics import AnalyticsService, ForecastService
from app.db.models.company import GoalScopeType


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


class TestAnalytics:
    def test_workforce_analytics(self, db: Session) -> None:
        company = _make_company(db)
        svc = AnalyticsService(db)
        result = svc.workforce_analytics(company.id)
        assert result["total_employees"] == 0
        assert result["total_departments"] == 0

    def test_operations_analytics_empty(self, db: Session) -> None:
        company = _make_company(db)
        svc = AnalyticsService(db)
        result = svc.operations_analytics(company.id)
        assert result["total_tasks"] == 0
        assert result["success_rate"] == 0.0

    def test_reliability_analytics_empty(self, db: Session) -> None:
        company = _make_company(db)
        svc = AnalyticsService(db)
        result = svc.reliability_analytics(company.id)
        assert result["verification_rate"] == 0.0
        assert result["recovery_rate"] == 0.0

    def test_finance_analytics_no_budget(self, db: Session) -> None:
        company = _make_company(db)
        svc = AnalyticsService(db)
        result = svc.finance_analytics(company.id)
        assert result["total_spend"] == 0.0

    def test_finance_analytics_with_budget(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.budget import BudgetManager

        bm = BudgetManager(db)
        budget = bm.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 1000.0)
        bm.spend(budget, cost=200.0, tokens=500, tool_calls=10)
        svc = AnalyticsService(db)
        result = svc.finance_analytics(company.id)
        assert result["total_spend"] == 200.0
        assert result["budget_utilization"] == 20.0
        assert result["tokens_used"] == 500

    def test_strategy_analytics(self, db: Session) -> None:
        company = _make_company(db)
        svc = AnalyticsService(db)
        result = svc.strategy_analytics(company.id)
        assert "goal_progress" in result
        assert "risk_distribution" in result

    def test_full_analytics(self, db: Session) -> None:
        company = _make_company(db)
        svc = AnalyticsService(db)
        result = svc.full_analytics(company.id)
        assert "workforce" in result
        assert "operations" in result
        assert "reliability" in result
        assert "finance" in result
        assert "strategy" in result


class TestForecast:
    def test_budget_forecast_no_budget(self, db: Session) -> None:
        company = _make_company(db)
        svc = ForecastService(db)
        result = svc.budget_forecast(company.id)
        assert result["projected_spend"] == 0.0

    def test_budget_forecast_with_spend(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.budget import BudgetManager

        bm = BudgetManager(db)
        budget = bm.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 1000.0)
        bm.spend(budget, cost=100.0)
        svc = ForecastService(db)
        result = svc.budget_forecast(company.id)
        assert result["current_spend"] == 100.0
        assert "daily_burn_rate" in result
        assert "on_track" in result

    def test_goal_forecast_not_found(self, db: Session) -> None:
        svc = ForecastService(db)
        result = svc.goal_forecast(uuid4())
        assert "error" in result
