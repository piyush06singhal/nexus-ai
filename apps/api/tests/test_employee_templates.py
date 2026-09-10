"""Tests for AI Employee templates (Phase 7)."""

from app.employee.manager import EmployeeManager


def test_create_template(db):
    mgr = EmployeeManager(db)
    template = mgr.templates.create_template(
        name="Research Analyst",
        description="Market research specialist",
        role="analyst",
        skills=[{"skill_id": "r1", "name": "research", "proficiency": 0.8}],
        responsibilities=["Conduct market research"],
        tools=["web_search"],
        policies={"max_concurrent_tasks": 3},
    )
    assert template.name == "Research Analyst"
    assert template.role == "analyst"


def test_list_templates(db):
    mgr = EmployeeManager(db)
    mgr.templates.create_template(name="T1", role="a")
    mgr.templates.create_template(name="T2", role="b")
    templates = mgr.templates.list_templates()
    assert len(templates) == 2


def test_get_template(db):
    mgr = EmployeeManager(db)
    t = mgr.templates.create_template(name="Specific", role="dev")
    fetched = mgr.templates.get_template(t.id)
    assert fetched.id == t.id


def test_create_employee_from_template(db):
    mgr = EmployeeManager(db)
    template = mgr.templates.create_template(
        name="Analyst",
        role="analyst",
        skills=[{"skill_id": "r1", "name": "research"}],
        responsibilities=["Research"],
        tools=["web_search"],
    )
    emp = mgr.templates.create_employee_from_template(template.id, name="alex-analyst")
    assert emp is not None
    assert emp.role == "analyst"
    # Cloned config present
    from app.employee.skills import SkillAssessor

    skills = SkillAssessor(db).get_skills(emp.id)
    assert len(skills) == 1
    assert skills[0].name == "research"
    # Fresh identity: status draft, distinct namespace
    from app.db.models.employee import EmployeeStatus

    assert emp.status == EmployeeStatus.DRAFT
    assert emp.memory_namespace == "employee:alex-analyst"


def test_create_from_template_applies_overrides(db):
    mgr = EmployeeManager(db)
    template = mgr.templates.create_template(
        name="Base",
        role="analyst",
        skills=[{"skill_id": "s1", "name": "python"}],
    )
    emp = mgr.templates.create_employee_from_template(
        template.id,
        name="overridden",
        overrides={"role": "engineer", "skills": [{"skill_id": "s2", "name": "java"}]},
    )
    assert emp.role == "engineer"
    from app.employee.skills import SkillAssessor

    skills = SkillAssessor(db).get_skills(emp.id)
    assert skills[0].name == "java"


def test_create_from_nonexistent_template_returns_none(db):
    from uuid import uuid4

    mgr = EmployeeManager(db)
    assert mgr.templates.create_employee_from_template(uuid4(), name="x") is None
