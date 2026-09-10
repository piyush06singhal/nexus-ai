"""Tests for AI Employee skills (Phase 7)."""

from app.employee.manager import EmployeeManager
from app.employee.skills import SkillAssessor
from app.employee.types import SkillEntry


def test_add_and_get_skill(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="skill-worker")
    skill = SkillEntry(skill_id="s1", name="python", category="coding", proficiency=0.4)
    mgr.add_skill(emp.id, skill)

    skills = mgr.get_skills(emp.id)
    assert len(skills) == 1
    assert skills[0].name == "python"
    assert skills[0].proficiency == 0.4


def test_skill_added_updates_existing_not_duplicate(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="skill-updater")
    svc = SkillAssessor(db)
    svc.add_skill(emp.id, SkillEntry(skill_id="s1", name="python", proficiency=0.2))
    svc.add_skill(emp.id, SkillEntry(skill_id="s1", name="python", proficiency=0.8))

    skills = svc.get_skills(emp.id)
    assert len(skills) == 1
    assert skills[0].proficiency == 0.8


def test_remove_skill(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="skill-remover")
    svc = SkillAssessor(db)
    svc.add_skill(emp.id, SkillEntry(skill_id="s1", name="python"))
    svc.add_skill(emp.id, SkillEntry(skill_id="s2", name="sql"))

    assert svc.remove_skill(emp.id, "s1")
    skills = svc.get_skills(emp.id)
    assert len(skills) == 1
    assert skills[0].skill_id == "s2"


def test_remove_nonexistent_skill_returns_false(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="skill-nothing")
    assert mgr.skills.remove_skill(emp.id, "nope") is False


def test_record_skill_use_increases_proficiency(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="skill-learner")
    svc = SkillAssessor(db)
    svc.add_skill(emp.id, SkillEntry(skill_id="s1", name="python", proficiency=0.3))

    updated = svc.record_skill_use(emp.id, "s1", success=True, quality=0.9)
    assert updated is not None
    assert updated.proficiency > 0.3
    assert updated.evidence_count == 1


def test_record_skill_use_failure_decreases(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="skill-failure")
    svc = SkillAssessor(db)
    svc.add_skill(emp.id, SkillEntry(skill_id="s1", name="python", proficiency=0.8))

    updated = svc.record_skill_use(emp.id, "s1", success=False)
    assert updated is not None
    assert updated.proficiency < 0.8


def test_match_skills(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="skill-matcher")
    svc = SkillAssessor(db)
    svc.add_skill(emp.id, SkillEntry(skill_id="s1", name="Python", proficiency=0.9))
    svc.add_skill(emp.id, SkillEntry(skill_id="s2", name="SQL", proficiency=0.5))

    score, matched = svc.match_skills(emp.id, ["python", "sql", "java"])
    # 2 of 3 matched
    assert abs(score - (2 / 3)) < 1e-6
    assert set(matched) == {"python", "sql"}


def test_match_skills_empty_requirements(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="skill-none")
    score, _ = mgr.skills.match_skills(emp.id, [])
    assert score == 1.0
