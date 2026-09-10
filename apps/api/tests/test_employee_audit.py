"""Tests for AI Employee audit logging (Phase 7)."""

from app.employee.manager import EmployeeManager


def test_create_employee_logs_event(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="audit-create")

    audit = mgr.get_audit_log(emp.id)
    actions = [a["action"] for a in audit]
    assert "created" in actions


def test_activate_logs_event(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="audit-activate")
    mgr.activate(emp.id)

    audit = mgr.get_audit_log(emp.id)
    actions = [a["action"] for a in audit]
    assert "activated" in actions


def test_terminate_logs_event(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="audit-terminate")
    mgr.activate(emp.id)
    mgr.terminate(emp.id)

    audit = mgr.get_audit_log(emp.id)
    actions = [a["action"] for a in audit]
    assert "terminated" in actions


def test_goal_created_logged(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="audit-goal")
    mgr.create_goal(emp.id, title="Ship X")

    audit = mgr.get_audit_log(emp.id)
    actions = [a["action"] for a in audit]
    assert "goal_created" in actions


def test_skill_added_logged(db):
    from app.employee.types import SkillEntry

    mgr = EmployeeManager(db)
    emp = mgr.create(name="audit-skill")
    mgr.add_skill(emp.id, SkillEntry(skill_id="s1", name="python"))

    audit = mgr.get_audit_log(emp.id)
    actions = [a["action"] for a in audit]
    assert "skill_added" in actions


def test_audit_log_limit(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="audit-limit")
    mgr.activate(emp.id)
    mgr.pause(emp.id)
    mgr.resume(emp.id)

    entries = mgr.get_audit_log(emp.id, limit=2)
    assert len(entries) == 2


def test_audit_details_parsed(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="audit-details")

    audit = mgr.get_audit_log(emp.id)
    created = [a for a in audit if a["action"] == "created"][0]
    assert created["details"]["name"] == "audit-details"
    assert created["outcome"] == "success"


def test_employee_timeline_returns_events(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="timeline-worker")
    mgr.activate(emp.id)

    timeline = mgr.get_timeline(emp.id)
    assert len(timeline) >= 2
    types = {t["event_type"] for t in timeline}
    assert "created" in types
    assert "activated" in types
