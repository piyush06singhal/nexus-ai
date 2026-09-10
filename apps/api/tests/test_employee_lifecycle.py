"""Tests for AI Employee lifecycle state machine (Phase 7)."""

import pytest

from app.db.models.employee import EmployeeStatus
from app.employee.lifecycle import (
    EmployeeLifecycleError,
    can_transition,
    is_available_for_tasks,
    validate_transition,
)
from app.employee.manager import EmployeeManager

# ── Pure state machine tests ──────────────────────────────────────────────────


def test_draft_can_activate():
    assert can_transition(EmployeeStatus.DRAFT, EmployeeStatus.ACTIVE)


def test_draft_cannot_skip_to_busy():
    assert not can_transition(EmployeeStatus.DRAFT, EmployeeStatus.BUSY)
    with pytest.raises(EmployeeLifecycleError):
        validate_transition(EmployeeStatus.DRAFT, EmployeeStatus.BUSY)


def test_active_can_pause_suspend_terminate():
    for target in (EmployeeStatus.PAUSED, EmployeeStatus.SUSPENDED, EmployeeStatus.TERMINATED):
        assert can_transition(EmployeeStatus.ACTIVE, target)


def test_terminated_is_final():
    assert not can_transition(EmployeeStatus.TERMINATED, EmployeeStatus.ACTIVE)
    assert not can_transition(EmployeeStatus.TERMINATED, EmployeeStatus.PAUSED)


def test_any_non_draft_can_transition_to_terminated():
    """DRAFT cannot go directly to TERMINATED — must activate first."""
    for s in (
        EmployeeStatus.ACTIVE,
        EmployeeStatus.BUSY,
        EmployeeStatus.PAUSED,
        EmployeeStatus.ON_LEAVE,
        EmployeeStatus.SUSPENDED,
    ):
        assert can_transition(s, EmployeeStatus.TERMINATED)
    # Draft → terminated is NOT valid (must go through active first)
    assert not can_transition(EmployeeStatus.DRAFT, EmployeeStatus.TERMINATED)


def test_is_available_for_tasks():
    assert is_available_for_tasks(EmployeeStatus.ACTIVE)
    assert is_available_for_tasks(EmployeeStatus.BUSY)
    assert not is_available_for_tasks(EmployeeStatus.TERMINATED)
    assert not is_available_for_tasks(EmployeeStatus.PAUSED)
    assert not is_available_for_tasks(EmployeeStatus.DRAFT)


# ── Manager integration tests ─────────────────────────────────────────────────


def test_full_lifecycle_cycle(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="alice", role="analyst")
    assert emp.status == EmployeeStatus.DRAFT

    mgr.activate(emp.id)
    assert emp.status == EmployeeStatus.ACTIVE

    mgr.pause(emp.id)
    assert emp.status == EmployeeStatus.PAUSED

    mgr.resume(emp.id)
    assert emp.status == EmployeeStatus.ACTIVE

    mgr.terminate(emp.id)
    assert emp.status == EmployeeStatus.TERMINATED


def test_invalid_transition_raises(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="bob")
    # DRAFT → TERMINATED is invalid per the state machine.
    with pytest.raises(EmployeeLifecycleError):
        mgr.terminate(emp.id)


def test_terminated_cannot_reactivate(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="carol")
    mgr.activate(emp.id)
    mgr.pause(emp.id)
    mgr.resume(emp.id)
    mgr.terminate(emp.id)
    # Terminated is final — reactivation must raise.
    with pytest.raises(EmployeeLifecycleError):
        mgr.activate(emp.id)


def test_create_sets_budget(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="dave")
    from sqlalchemy import select

    from app.db.models.employee import EmployeeBudget

    stmt = select(EmployeeBudget).where(EmployeeBudget.employee_id == emp.id)
    budgets = list(db.execute(stmt).scalars())
    assert len(budgets) == 1
    assert budgets[0].monthly_limit == 50.0


def test_create_and_get(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="eve")
    fetched = mgr.get(emp.id)
    assert fetched.id == emp.id
    assert fetched.memory_namespace == "employee:eve"


def test_list_filters_by_status(db):
    mgr = EmployeeManager(db)
    a = mgr.create(name="frank")
    b = mgr.create(name="grace")
    mgr.activate(a.id)
    statuses = mgr.list_(status=EmployeeStatus.ACTIVE)
    assert [e.id for e in statuses] == [a.id]

    all_emps = {e.id for e in mgr.list_()}
    assert {a.id, b.id} <= all_emps
