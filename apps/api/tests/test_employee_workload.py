"""Tests for AI Employee workload management (Phase 7)."""

from app.employee.manager import EmployeeManager
from app.employee.types import AssignmentRequest, WorkloadSnapshot


def test_workload_snapshot(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="busy-worker")
    mgr.activate(emp.id)

    snap = mgr.get_workload(emp.id)
    assert isinstance(snap, WorkloadSnapshot)
    assert snap.capacity == 5
    assert snap.active_tasks == 0
    assert snap.available_slots == 5
    assert snap.utilization == 0.0


def test_workload_counts_queued_tasks_after_assignment(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="loaded-worker")
    mgr.activate(emp.id)

    mgr.assign_task_to(emp.id, AssignmentRequest(task_title="Task one"))
    snap = mgr.get_workload(emp.id)
    assert snap.queued_tasks == 1
    assert snap.active_tasks == 0


def test_workload_counts_completed_tasks(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="done-worker")
    mgr.activate(emp.id)

    result = mgr.assign_task_to(emp.id, AssignmentRequest(task_title="Do it"))
    assert result.task_id is not None

    # Mark the task completed directly to simulate a finished execution.
    from app.services.task_service import TaskService

    TaskService(db).mark_completed(result.task_id)
    snap = mgr.get_workload(emp.id)
    assert snap.completed_tasks == 1
    assert snap.queued_tasks == 0


def test_can_accept_task_with_capacity(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="capacity-worker")
    mgr.activate(emp.id)

    assert mgr.workload.can_accept_task(emp.id) is True


def test_cannot_accept_task_when_draft(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="draft-worker")
    # Not activated → still DRAFT
    assert mgr.workload.can_accept_task(emp.id) is False


def test_cannot_accept_task_when_terminated(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="gone-worker")
    mgr.activate(emp.id)
    mgr.terminate(emp.id)
    assert mgr.workload.can_accept_task(emp.id) is False


def test_workload_config_capacity(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="config-worker")
    # Update workload_config to set a smaller capacity
    mgr.update(emp.id, workload_config={"max_concurrent": 2})
    snap = mgr.get_workload(emp.id)
    assert snap.capacity == 2


def test_get_available_employees_only_active(db):
    mgr = EmployeeManager(db)
    a = mgr.create(name="active-worker")
    b = mgr.create(name="draft-worker")
    mgr.activate(a.id)

    available = mgr.workload.get_available_employees()
    assert a.id in available
    assert b.id not in available
