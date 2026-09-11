"""Tests for AI Company Layer — risk management."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.company.risks import RiskManager
from app.db.models.company import GoalScopeType, RiskStatus


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


class TestRiskCRUD:
    def test_create_risk(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RiskManager(db)
        risk = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Budget overrun",
            severity="high",
            probability=0.7,
            impact="Financial",
        )
        assert risk.title == "Budget overrun"
        assert risk.severity == "high"
        assert risk.status == RiskStatus.OPEN

    def test_create_invalid_severity(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RiskManager(db)
        with pytest.raises(ValueError, match="Invalid severity"):
            mgr.create(
                company_id=company.id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company.id,
                title="Risk",
                severity="banana",
            )

    def test_list_risks(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RiskManager(db)
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Risk 1",
            severity="low",
        )
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Risk 2",
            severity="critical",
        )
        risks = mgr.list_(company.id)
        assert len(risks) == 2

    def test_filter_by_severity(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RiskManager(db)
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Low Risk",
            severity="low",
        )
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Critical Risk",
            severity="critical",
        )
        criticals = mgr.list_(company.id, severity="critical")
        assert len(criticals) == 1
        assert criticals[0].title == "Critical Risk"


class TestRiskLifecycle:
    def test_update_status(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RiskManager(db)
        risk = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Risk",
        )
        updated = mgr.update_status(risk.id, RiskStatus.MITIGATING)
        assert updated.status == RiskStatus.MITIGATING

    def test_update_severity(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RiskManager(db)
        risk = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Risk",
            severity="low",
        )
        updated = mgr.update_severity(risk.id, "critical")
        assert updated.severity == "critical"

    def test_update_mitigation(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RiskManager(db)
        risk = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Risk",
        )
        updated = mgr.update_mitigation(risk.id, "Add monitoring")
        assert updated.mitigation == "Add monitoring"

    def test_top_risks(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RiskManager(db)
        for sev in ["low", "medium", "critical", "high"]:
            mgr.create(
                company_id=company.id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company.id,
                title=f"{sev} risk",
                severity=sev,
            )
        top = mgr.top_risks(company.id, limit=2)
        assert len(top) == 2
        assert top[0].severity == "critical"
        assert top[1].severity == "high"

    def test_to_dict(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RiskManager(db)
        risk = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Budget Risk",
            severity="high",
        )
        d = mgr.to_dict(risk)
        assert d["title"] == "Budget Risk"
        assert d["severity"] == "high"
        assert d["status"] == "open"
