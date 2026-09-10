"""Tests for AI Employee assignment engine (Phase 7)."""

from app.db.models.employee import EmployeeStatus
from app.employee.manager import EmployeeManager
from app.employee.types import (
    AssignmentRequest,
    SkillEntry,
)


def _make_employee(mgr, name, role="analyst"):
    emp = mgr.create(name=name, role=role)
    mgr.activate(emp.id)
    return emp


def test_auto_assign_picks_best_skill_match(db):
    mgr = EmployeeManager(db)
    emp_python = _make_employee(mgr, "python-worker")
    emp_sql = _make_employee(mgr, "sql-worker")
    _make_employee(mgr, "frank")

    mgr.skills.add_skill(emp_python.id, SkillEntry(skill_id="s1", name="python", proficiency=0.9))
    mgr.skills.add_skill(emp_sql.id, SkillEntry(skill_id="s2", name="sql", proficiency=0.9))

    req = AssignmentRequest(
        task_title="Write python script",
        required_skills=["python"],
    )
    result = mgr.assign_task(req)
    assert result.success
    assert result.employee_id == emp_python.id
    assert result.score > 0


def test_auto_assign_prefers_preferred_role(db):
    mgr = EmployeeManager(db)
    _make_employee(mgr, "sales-person", role="sales")
    emp_dev = _make_employee(mgr, "developer", role="developer")

    req = AssignmentRequest(
        task_title="Build feature",
        preferred_role="developer",
    )
    result = mgr.assign_task(req)
    assert result.success
    assert result.employee_id == emp_dev.id


def test_assign_specific(db):
    mgr = EmployeeManager(db)
    emp = _make_employee(mgr, "specific-worker")

    req = AssignmentRequest(task_title="Specific task")
    result = mgr.assign_task_to(emp.id, req)
    assert result.success
    assert result.employee_id == emp.id


def test_assign_to_terminated_fails(db):
    mgr = EmployeeManager(db)
    emp = _make_employee(mgr, "terminated-worker")
    mgr.terminate(emp.id)

    req = AssignmentRequest(task_title="T")
    result = mgr.assign_task_to(emp.id, req)
    assert not result.success


def test_assign_to_nonexistent_fails(db):
    mgr = EmployeeManager(db)
    from uuid import uuid4

    req = AssignmentRequest(task_title="T")
    result = mgr.assign_task_to(uuid4(), req)
    assert not result.success


def test_no_active_candidates_fails(db):
    mgr = EmployeeManager(db)
    _make_employee(mgr, "draft-worker")
    # Only one employee; keep them DRAFT (not activated).
    from sqlalchemy import select

    from app.db.models.employee import AIEmployee

    emp = db.execute(select(AIEmployee)).scalars().first()
    emp.status = EmployeeStatus.DRAFT
    db.flush()

    req = AssignmentRequest(task_title="T", required_skills=["python"])
    result = mgr.assign_task(req)
    assert not result.success


def test_assignment_records_audit_event(db):
    mgr = EmployeeManager(db)
    emp = _make_employee(mgr, "audit-worker")
    req = AssignmentRequest(task_title="Audited task")
    result = mgr.assign_task_to(emp.id, req)
    assert result.success

    audit = mgr.get_audit_log(emp.id)
    actions = [a["action"] for a in audit]
    assert "task_assigned" in actions


def test_assignment_explainable(db):
    mgr = EmployeeManager(db)
    emp = _make_employee(mgr, "explainable")
    mgr.skills.add_skill(emp.id, SkillEntry(skill_id="s1", name="research", proficiency=0.7))

    req = AssignmentRequest(task_title="Research X", required_skills=["research"])
    result = mgr.assign_task(req)
    assert result.success
    assert "skill_match" in result.reasoning
    assert result.candidates_evaluated >= 1


def test_specific_assignment_creates_real_task(db):
    """Assignment must persist a real Task owned by the employee's agent."""
    from sqlalchemy import select

    from app.db.models.task import Task

    mgr = EmployeeManager(db)
    emp = _make_employee(mgr, "real-task-worker")
    assert emp.agent_id is not None  # backing agent auto-created

    req = AssignmentRequest(task_title="Real work")
    result = mgr.assign_task_to(emp.id, req)
    assert result.success
    assert result.task_id is not None

    task = db.execute(select(Task).where(Task.id == result.task_id)).scalar_one()
    assert task.assigned_agent_id == emp.agent_id
    assert task.status.value == "queued"


def test_auto_assignment_creates_real_task(db):
    from sqlalchemy import select

    from app.db.models.task import Task

    mgr = EmployeeManager(db)
    _make_employee(mgr, "auto-real-a")
    _make_employee(mgr, "auto-real-b")

    req = AssignmentRequest(task_title="Auto real work")
    result = mgr.assign_task(req)
    assert result.success
    assert result.task_id is not None

    task = db.execute(select(Task).where(Task.id == result.task_id)).scalar_one()
    assert task.assigned_agent_id is not None
    assert task.status.value == "queued"


def test_task_inbox_returns_real_tasks(db):
    mgr = EmployeeManager(db)
    emp = _make_employee(mgr, "inbox-worker")

    mgr.assign_task_to(emp.id, AssignmentRequest(task_title="Inbox one"))
    mgr.assign_task_to(emp.id, AssignmentRequest(task_title="Inbox two"))

    tasks = mgr.get_tasks(emp.id)
    assert len(tasks) == 2
    assert all(t["assigned_agent_id"] == str(emp.agent_id) for t in tasks)


def test_performance_score_uses_real_success_rate(db):
    """Higher real success rate should upgrade the perf component (10%)."""
    mgr = EmployeeManager(db)

    # Employee with proven performance (recorded completions).
    good = mgr.create(name="good-record")
    mgr.activate(good.id)
    mgr.add_skill(good.id, SkillEntry(skill_id="s1", name="research", proficiency=0.9))
    mgr.performance.record_task_completion(good.id, success=True)
    mgr.performance.record_task_completion(good.id, success=True)
    mgr.performance.record_task_completion(good.id, success=True)

    # Employee with no record → success rate 0.0.
    fresh = mgr.create(name="fresh-record")
    mgr.activate(fresh.id)
    mgr.add_skill(fresh.id, SkillEntry(skill_id="s1", name="research", proficiency=0.9))

    req = AssignmentRequest(task_title="Perf task", required_skills=["research"])
    result = mgr.assign_task(req)
    assert result.success
    # The proven employee should score higher than the fresh one.
    assert result.employee_id == good.id
