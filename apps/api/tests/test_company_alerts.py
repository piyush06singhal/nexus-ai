"""Tests for AI Company Layer — alerts, thresholds, and company health."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.company.alerts import AlertManager, CompanyHealth
from app.db.models.company import (
    AlertSeverity,
    AlertStatus,
    GoalScopeType,
)


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


class TestAlertCRUD:
    def test_create_alert(self, db: Session) -> None:
        company = _make_company(db)
        mgr = AlertManager(db)
        alert = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Budget Warning",
            severity=AlertSeverity.WARNING,
            category="budget",
            message="Spend at 85%",
        )
        assert alert.status == AlertStatus.ACTIVE
        assert alert.severity == AlertSeverity.WARNING

    def test_acknowledge_alert(self, db: Session) -> None:
        company = _make_company(db)
        mgr = AlertManager(db)
        alert = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Alert",
            severity=AlertSeverity.WARNING,
            category="test",
            message="msg",
        )
        acked = mgr.acknowledge(alert.id)
        assert acked.status == AlertStatus.ACKNOWLEDGED

    def test_resolve_alert(self, db: Session) -> None:
        company = _make_company(db)
        mgr = AlertManager(db)
        alert = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Alert",
            severity=AlertSeverity.CRITICAL,
            category="test",
            message="msg",
        )
        resolved = mgr.resolve(alert.id)
        assert resolved.status == AlertStatus.RESOLVED
        assert resolved.resolved_at is not None

    def test_list_alerts(self, db: Session) -> None:
        company = _make_company(db)
        mgr = AlertManager(db)
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="A1",
            severity=AlertSeverity.WARNING,
            category="budget",
            message="msg",
        )
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="A2",
            severity=AlertSeverity.CRITICAL,
            category="reliability",
            message="msg",
        )
        all_alerts = mgr.list_(company.id)
        assert len(all_alerts) == 2
        budget_alerts = mgr.list_(company.id, category="budget")
        assert len(budget_alerts) == 1

    def test_to_dict(self, db: Session) -> None:
        company = _make_company(db)
        mgr = AlertManager(db)
        alert = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Alert",
            severity=AlertSeverity.WARNING,
            category="budget",
            message="msg",
            payload={"utilization": 85.0},
        )
        d = mgr.to_dict(alert)
        assert d["title"] == "Alert"
        assert d["payload"]["utilization"] == 85.0


class TestAlertThresholds:
    def test_budget_over_80_generates_alert(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.budget import BudgetManager

        bm = BudgetManager(db)
        budget = bm.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        bm.spend(budget, cost=85.0)  # 85% utilization
        mgr = AlertManager(db)
        alerts = mgr.generate_alerts(company.id)
        budget_alerts = [a for a in alerts if a.category == "budget"]
        assert len(budget_alerts) == 1
        assert budget_alerts[0].severity == AlertSeverity.WARNING

    def test_budget_over_95_is_critical(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.budget import BudgetManager

        bm = BudgetManager(db)
        budget = bm.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        bm.spend(budget, cost=97.0)  # 97% utilization
        mgr = AlertManager(db)
        alerts = mgr.generate_alerts(company.id)
        budget_alerts = [a for a in alerts if a.category == "budget"]
        assert len(budget_alerts) == 1
        assert budget_alerts[0].severity == AlertSeverity.CRITICAL

    def test_no_alert_when_under_80(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.budget import BudgetManager

        bm = BudgetManager(db)
        budget = bm.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 100.0)
        bm.spend(budget, cost=50.0)  # 50% utilization
        mgr = AlertManager(db)
        alerts = mgr.generate_alerts(company.id)
        budget_alerts = [a for a in alerts if a.category == "budget"]
        assert len(budget_alerts) == 0


class TestCompanyHealth:
    def test_compute_empty_company(self, db: Session) -> None:
        company = _make_company(db)
        health = CompanyHealth(db).compute(company.id)
        assert "overall_score" in health
        assert "dimensions" in health
        assert "status" in health
        # No data → neutral scores → healthy
        assert health["status"] in ("healthy", "degraded", "critical")

    def test_explain(self, db: Session) -> None:
        company = _make_company(db)
        result = CompanyHealth(db).explain(company.id)
        assert "health" in result
        assert "explanations" in result
        assert isinstance(result["explanations"], dict)

    def test_weights_sum_to_100(self) -> None:
        assert sum(CompanyHealth.WEIGHTS.values()) == 100

    def test_health_with_budget(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.budget import BudgetManager

        bm = BudgetManager(db)
        budget = bm.ensure_budget(company.id, GoalScopeType.COMPANY, company.id, 1000.0)
        bm.spend(budget, cost=100.0)  # 10% utilization → healthy cost score
        health = CompanyHealth(db).compute(company.id)
        assert health["dimensions"]["cost"] == 90.0  # 100 - 10%
