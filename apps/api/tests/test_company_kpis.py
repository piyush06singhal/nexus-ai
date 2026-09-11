"""Tests for AI Company Layer — KPIs computed from authoritative sources."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.company.kpis import SOURCE_METRICS, KPIService
from app.db.models.company import GoalScopeType, KpiCategory


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


class TestKPICRUD:
    def test_create_kpi(self, db: Session) -> None:
        company = _make_company(db)
        svc = KPIService(db)
        kpi = svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="Task Success",
            source_metric="task_success_rate",
            target=95.0,
        )
        assert kpi.name == "Task Success"
        assert kpi.source_metric == "task_success_rate"
        assert kpi.category == KpiCategory.QUALITY
        assert kpi.unit == "%"

    def test_create_kpi_unknown_source(self, db: Session) -> None:
        company = _make_company(db)
        svc = KPIService(db)
        with pytest.raises(ValueError, match="Unknown source_metric"):
            svc.create(
                company_id=company.id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company.id,
                name="Bad",
                source_metric="nonexistent_metric",
            )

    def test_list_kpis(self, db: Session) -> None:
        company = _make_company(db)
        svc = KPIService(db)
        svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="KPI 1",
            source_metric="task_volume",
        )
        svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="KPI 2",
            source_metric="total_cost",
        )
        kpis = svc.list_(company.id)
        assert len(kpis) == 2

    def test_source_metrics_registry(self) -> None:
        assert "task_success_rate" in SOURCE_METRICS
        assert "verification_rate" in SOURCE_METRICS
        assert "total_cost" in SOURCE_METRICS


class TestKPIComputation:
    def test_recompute_empty_db(self, db: Session) -> None:
        """No agents/tasks → KPI value should be 0."""
        company = _make_company(db)
        svc = KPIService(db)
        kpi = svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="Success Rate",
            source_metric="task_success_rate",
            target=90.0,
        )
        reading = svc.recompute(kpi)
        assert reading.value == 0.0
        assert reading.variance == -90.0  # 0 - 90 target

    def test_recompute_all(self, db: Session) -> None:
        company = _make_company(db)
        svc = KPIService(db)
        svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="Volume",
            source_metric="task_volume",
        )
        readings = svc.recompute_all(company.id)
        assert len(readings) == 1
        assert readings[0].value == 0.0

    def test_snapshot_empty(self, db: Session) -> None:
        company = _make_company(db)
        svc = KPIService(db)
        kpi = svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="KPI",
            source_metric="task_volume",
        )
        snap = svc.snapshot(kpi)
        assert snap["current_value"] is None
        assert snap["history"] == []

    def test_snapshot_with_history(self, db: Session) -> None:
        company = _make_company(db)
        svc = KPIService(db)
        kpi = svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="KPI",
            source_metric="task_volume",
        )
        svc.recompute(kpi)
        svc.recompute(kpi)
        snap = svc.snapshot(kpi)
        assert len(snap["history"]) == 2
        assert snap["current_value"] == 0.0

    def test_trend_computation(self, db: Session) -> None:
        company = _make_company(db)
        svc = KPIService(db)
        kpi = svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="KPI",
            source_metric="active_employees",
        )
        reading1 = svc.recompute(kpi)
        assert reading1.trend == "flat"  # First reading = flat
        reading2 = svc.recompute(kpi)
        assert reading2.trend == "flat"  # Same value = flat

    def test_no_target_means_no_variance(self, db: Session) -> None:
        company = _make_company(db)
        svc = KPIService(db)
        kpi = svc.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            name="KPI",
            source_metric="task_volume",
        )
        reading = svc.recompute(kpi)
        assert reading.variance is None
