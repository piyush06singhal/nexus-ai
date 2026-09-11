"""Tests for AI Company Layer — report generation and verification."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.company.reports import ReportGenerator


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


class TestReportGeneration:
    def test_generate_weekly_report(self, db: Session) -> None:
        company = _make_company(db)
        gen = ReportGenerator(db)
        report = gen.generate(company.id, report_type="weekly")
        assert report.company_id == company.id
        assert report.report_type == "weekly"
        assert report.verification_status == "unverified"

    def test_verify_report(self, db: Session) -> None:
        company = _make_company(db)
        gen = ReportGenerator(db)
        report = gen.generate(company.id, report_type="weekly")
        verified, summary = gen.verify(report)
        # Empty company → no tasks → all zeros match
        assert verified is True
        assert "match" in summary.lower()

    def test_list_reports(self, db: Session) -> None:
        company = _make_company(db)
        gen = ReportGenerator(db)
        gen.generate(company.id, report_type="weekly")
        gen.generate(company.id, report_type="health")
        reports = gen.list_(company.id)
        assert len(reports) == 2

    def test_list_reports_filtered(self, db: Session) -> None:
        company = _make_company(db)
        gen = ReportGenerator(db)
        gen.generate(company.id, report_type="weekly")
        gen.generate(company.id, report_type="health")
        weekly = gen.list_(company.id, report_type="weekly")
        assert len(weekly) == 1
        assert weekly[0].report_type == "weekly"

    def test_to_dict(self, db: Session) -> None:
        company = _make_company(db)
        gen = ReportGenerator(db)
        report = gen.generate(company.id, report_type="weekly")
        d = gen.to_dict(report)
        assert d["report_type"] == "weekly"
        assert "metrics" in d
        assert "highlights" in d
        assert "recommendations" in d
        assert "evidence" in d
        assert d["verification_status"] == "unverified"

    def test_recommendations_are_non_executing(self, db: Session) -> None:
        """Reports must never auto-execute recommendations (§28)."""
        company = _make_company(db)
        gen = ReportGenerator(db)
        report = gen.generate(company.id)
        d = gen.to_dict(report)
        # Recommendations should be strings, not executable actions
        for rec in d.get("recommendations", []):
            assert isinstance(rec, str)
            assert len(rec) > 0
