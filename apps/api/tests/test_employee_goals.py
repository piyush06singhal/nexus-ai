"""Tests for AI Employee goals (Phase 7)."""

from app.db.models.employee import GoalStatus
from app.employee.manager import EmployeeManager
from app.employee.types import GoalStatus as DomainGoalStatus


def test_create_goal(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="goal-worker")
    goal = mgr.create_goal(emp.id, title="Ship feature X", priority=3)
    assert goal.employee_id == emp.id
    assert goal.title == "Ship feature X"
    assert goal.status == GoalStatus.NOT_STARTED
    assert goal.progress == 0.0


def test_list_goals_by_employee(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="goal-list")
    mgr.create_goal(emp.id, title="G1")
    mgr.create_goal(emp.id, title="G2")

    goals = mgr.get_goals(emp.id)
    assert len(goals) == 2
    assert {g.title for g in goals} == {"G1", "G2"}


def test_update_progress_activates_goal(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="goal-progress")
    goal = mgr.create_goal(emp.id, title="G")

    updated = mgr.goals.update_progress(goal.id, progress=0.5)
    assert updated.status == GoalStatus.ACTIVE
    assert updated.progress == 0.5


def test_update_progress_completes_at_100(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="goal-complete")
    goal = mgr.create_goal(emp.id, title="G")

    mgr.goals.update_progress(goal.id, progress=0.4)
    mgr.goals.update_progress(goal.id, progress=1.0)
    assert goal.status == GoalStatus.COMPLETED


def test_cancel_goal(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="goal-cancel")
    goal = mgr.create_goal(emp.id, title="G")

    mgr.goals.cancel_goal(goal.id)
    assert goal.status == GoalStatus.CANCELLED


def test_update_progress_clamps(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="goal-clamp")
    goal = mgr.create_goal(emp.id, title="G")

    mgr.goals.update_progress(goal.id, progress=1.5)
    assert goal.progress == 1.0

    mgr.goals.update_progress(goal.id, progress=-0.5)
    assert goal.progress == 0.0


def test_goal_filter_by_status(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="goal-filter")
    g1 = mgr.create_goal(emp.id, title="Active")
    mgr.create_goal(emp.id, title="Not started")

    mgr.goals.update_progress(g1.id, progress=0.5)

    # Filter for active goals
    goal_tracker = mgr.goals
    active = goal_tracker.get_goals(emp.id, status=DomainGoalStatus.ACTIVE)
    assert len(active) == 1
    assert active[0].title == "Active"


def test_overall_progress(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="goal-overall")
    g1 = mgr.create_goal(emp.id, title="G1")
    g2 = mgr.create_goal(emp.id, title="G2")

    mgr.goals.update_progress(g1.id, progress=0.5)
    mgr.goals.update_progress(g2.id, progress=0.3)

    overall = mgr.goals.overall_progress(emp.id)
    assert abs(overall - 0.4) < 1e-6
