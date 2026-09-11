"""Tests for AI Company Layer — organizational roles."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.company.roles import RoleManager
from app.db.models.company import AuthorityLevel


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    mgr = CompanyManager(db)
    return mgr.create(name="Test Co")


class TestRoleCRUD:
    def test_create_role(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RoleManager(db)
        role = mgr.create(
            company_id=company.id,
            name="engineer",
            title="Engineer",
            authority_level=AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
            responsibilities=["build software", "write tests"],
            required_skills=["python"],
        )
        assert role.name == "engineer"
        assert role.company_id == company.id
        assert role.authority_level == AuthorityLevel.INDIVIDUAL_CONTRIBUTOR

    def test_create_global_role(self, db: Session) -> None:
        mgr = RoleManager(db)
        role = mgr.create(
            company_id=None,
            name="global_admin",
            title="Global Admin",
            authority_level=AuthorityLevel.COMPANY_ADMIN,
        )
        assert role.company_id is None

    def test_list_roles(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RoleManager(db)
        mgr.create(company_id=company.id, name="eng", title="Engineer")
        mgr.create(company_id=company.id, name="mgr", title="Manager")
        roles = mgr.list_(company_id=company.id)
        assert len(roles) == 2

    def test_list_includes_global(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RoleManager(db)
        mgr.create(company_id=None, name="global", title="Global")
        mgr.create(company_id=company.id, name="local", title="Local")
        roles = mgr.list_(company_id=company.id)
        assert len(roles) == 2

    def test_filter_by_authority_level(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RoleManager(db)
        mgr.create(
            company_id=company.id,
            name="eng",
            title="Engineer",
            authority_level=AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        )
        mgr.create(
            company_id=company.id,
            name="mgr",
            title="Manager",
            authority_level=AuthorityLevel.MANAGER,
        )
        managers = mgr.list_(company_id=company.id, authority_level=AuthorityLevel.MANAGER)
        assert len(managers) == 1
        assert managers[0].name == "mgr"

    def test_find_by_name(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RoleManager(db)
        mgr.create(company_id=company.id, name="engineer", title="Engineer")
        found = mgr.find_by_name(company.id, "engineer")
        assert found is not None
        assert found.name == "engineer"

    def test_to_dict(self, db: Session) -> None:
        company = _make_company(db)
        mgr = RoleManager(db)
        role = mgr.create(
            company_id=company.id,
            name="engineer",
            title="Engineer",
            responsibilities=["code"],
            required_skills=["python", "sql"],
        )
        d = mgr.to_dict(role)
        assert d["name"] == "engineer"
        assert d["responsibilities"] == ["code"]
        assert d["required_skills"] == ["python", "sql"]
