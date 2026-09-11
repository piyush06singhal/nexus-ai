"""Tests for AI Company Layer — organization-aware task routing."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.company.membership import MembershipManager
from app.company.roles import RoleManager
from app.company.routing import OrgRoutingService
from app.db.models.agent import Agent
from app.db.models.company import AuthorityLevel
from app.db.models.employee import AIEmployee, EmployeeStatus


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


def _make_employee_with_agent(
    db: Session, name: str, skills: list[str] | None = None
) -> AIEmployee:
    import json

    agent = Agent(name=f"{name}-agent", model_name="test")
    db.add(agent)
    db.flush()
    emp = AIEmployee(
        name=name.lower(),
        display_name=name,
        role="engineer",
        status=EmployeeStatus.ACTIVE,
        skills=json.dumps(skills or ["python"]),
        agent_id=agent.id,
    )
    db.add(emp)
    db.commit()
    return emp


class TestOrgRouting:
    def test_route_to_best_candidate(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee_with_agent(db, "Alice", skills=["python", "ml"])
        role = RoleManager(db).create(
            company_id=company.id,
            name="eng",
            title="Engineer",
            authority_level=AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        )
        MembershipManager(db).add(
            company_id=company.id,
            employee_id=emp.id,
            role_id=role.id,
        )
        svc = OrgRoutingService(db)
        result = svc.route(
            company_id=company.id,
            task_name="Build ML pipeline",
            required_skills=["python", "ml"],
        )
        assert result["selected_employee_id"] == emp.id
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["score"] > 0

    def test_route_no_match(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee_with_agent(db, "Alice", skills=["python"])
        role = RoleManager(db).create(
            company_id=company.id,
            name="eng",
            title="Engineer",
        )
        MembershipManager(db).add(
            company_id=company.id,
            employee_id=emp.id,
            role_id=role.id,
        )
        svc = OrgRoutingService(db)
        result = svc.route(
            company_id=company.id,
            task_name="Design logo",
            required_skills=["design", "figma"],
        )
        assert result["selected_employee_id"] is None
        assert len(result["candidates"]) == 0

    def test_route_with_department_filter(self, db: Session) -> None:
        company = _make_company(db)
        from app.company.departments import DepartmentManager

        dept = DepartmentManager(db).create(company_id=company.id, name="Eng")
        emp = _make_employee_with_agent(db, "Alice", skills=["python"])
        role = RoleManager(db).create(company_id=company.id, name="eng", title="Eng")
        MembershipManager(db).add(
            company_id=company.id,
            employee_id=emp.id,
            department_id=dept.id,
            role_id=role.id,
        )
        svc = OrgRoutingService(db)
        result = svc.route(
            company_id=company.id,
            task_name="Write code",
            required_skills=["python"],
            department_id=dept.id,
        )
        assert result["selected_employee_id"] == emp.id

    def test_route_explainability(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee_with_agent(db, "Bob", skills=["python"])
        role = RoleManager(db).create(company_id=company.id, name="eng", title="Eng")
        MembershipManager(db).add(
            company_id=company.id,
            employee_id=emp.id,
            role_id=role.id,
        )
        svc = OrgRoutingService(db)
        result = svc.route(
            company_id=company.id,
            task_name="Test task",
        )
        assert "explainability" in result
        assert "timestamp" in result["explainability"]
        assert "score_breakdown" in result["explainability"]

    def test_route_candidates_have_breakdown(self, db: Session) -> None:
        company = _make_company(db)
        emp = _make_employee_with_agent(db, "E1", skills=["python", "sql"])
        role = RoleManager(db).create(
            company_id=company.id,
            name="eng",
            title="Eng",
            authority_level=AuthorityLevel.MANAGER,
        )
        MembershipManager(db).add(
            company_id=company.id,
            employee_id=emp.id,
            role_id=role.id,
        )
        svc = OrgRoutingService(db)
        result = svc.route(
            company_id=company.id,
            task_name="Analyze data",
            required_skills=["python"],
        )
        candidate = result["candidates"][0]
        assert "breakdown" in candidate
        assert "skill_match" in candidate["breakdown"]
        assert "authority" in candidate["breakdown"]
