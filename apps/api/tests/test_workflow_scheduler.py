"""Tests for the workflow trigger scheduler.

Deterministic — no real time waiting.  Triggers are given a ``next_run_at``
in the past and the scheduler is polled once directly.
"""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models.workflow import (
    TriggerType,
    WorkflowExecutionStatus,
    WorkflowStepType,
    WorkflowTrigger,
)
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowStepCreate,
    WorkflowTriggerCreate,
)
from app.services.workflow_service import WorkflowService
from app.workflow.scheduler import WorkflowScheduler, calculate_next_run


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, expire_on_commit=False)


def _make_active_workflow(svc, db, name):
    wf = svc.create(WorkflowCreate(name=name))
    svc.add_step(
        wf.id,
        WorkflowStepCreate(
            name="s1",
            step_type=WorkflowStepType.DELAY,
            configuration={"duration": 0},
        ),
    )
    svc.activate(wf.id)
    return wf


class TestScheduler:
    def test_scheduler_creates_execution_for_due_trigger(self, db, session_factory):
        svc = WorkflowService(db)
        wf = _make_active_workflow(svc, db, "sched-wf")
        trigger = svc.add_trigger(
            wf.id,
            WorkflowTriggerCreate(
                trigger_type=TriggerType.SCHEDULE,
                configuration={"interval": 60},
                enabled=True,
            ),
        )
        trigger.next_run_at = datetime.now(UTC) - timedelta(seconds=10)
        db.commit()

        scheduler = WorkflowScheduler(session_factory)
        scheduler._poll_once()

        executions = svc.list_executions(wf.id)
        assert len(executions) == 1
        assert executions[0].status == WorkflowExecutionStatus.QUEUED
        assert executions[0].trigger_type == "schedule"

    def test_scheduler_updates_next_run_at(self, db, session_factory):
        svc = WorkflowService(db)
        wf = _make_active_workflow(svc, db, "sched-wf2")
        trigger = svc.add_trigger(
            wf.id,
            WorkflowTriggerCreate(
                trigger_type=TriggerType.SCHEDULE,
                configuration={"interval": 60},
                enabled=True,
            ),
        )
        trigger.next_run_at = datetime.now(UTC) - timedelta(seconds=10)
        db.commit()
        old_next = trigger.next_run_at

        scheduler = WorkflowScheduler(session_factory)
        scheduler._poll_once()

        db.refresh(trigger)
        assert trigger.next_run_at is not None
        # next_run_at is advanced past the old next_run_at.  SQLite returns
        # naive datetimes, so coerce both sides for a safe comparison.
        new = trigger.next_run_at
        if new.tzinfo is None:
            new = new.replace(tzinfo=UTC)
        old = old_next
        if old.tzinfo is None:
            old = old.replace(tzinfo=UTC)
        assert new > old

    def test_scheduler_skips_disabled_trigger(self, db, session_factory):
        svc = WorkflowService(db)
        wf = _make_active_workflow(svc, db, "sched-wf3")
        trigger = svc.add_trigger(
            wf.id,
            WorkflowTriggerCreate(
                trigger_type=TriggerType.SCHEDULE,
                configuration={"interval": 60},
                enabled=False,
            ),
        )
        trigger.next_run_at = datetime.now(UTC) - timedelta(seconds=10)
        db.commit()

        scheduler = WorkflowScheduler(session_factory)
        scheduler._poll_once()

        executions = svc.list_executions(wf.id)
        assert len(executions) == 0

    def test_scheduler_skips_inactive_workflow(self, db, session_factory):
        svc = WorkflowService(db)
        # Keep this workflow DRAFT (not active) so its trigger must not fire.
        wf = svc.create(WorkflowCreate(name="sched-wf4"))
        trigger = svc.add_trigger(
            wf.id,
            WorkflowTriggerCreate(
                trigger_type=TriggerType.SCHEDULE,
                configuration={"interval": 60},
                enabled=True,
            ),
        )
        trigger.next_run_at = datetime.now(UTC) - timedelta(seconds=10)
        db.commit()

        scheduler = WorkflowScheduler(session_factory)
        scheduler._poll_once()

        executions = svc.list_executions(wf.id)
        assert len(executions) == 0

    def test_event_trigger_not_scheduled(self, db, session_factory):
        svc = WorkflowService(db)
        wf = _make_active_workflow(svc, db, "sched-wf5")
        svc.add_trigger(
            wf.id,
            WorkflowTriggerCreate(
                trigger_type=TriggerType.EVENT,
                configuration={"event_name": "new_leads"},
                enabled=True,
            ),
        )
        # No next_run_at set; scheduler must ignore event triggers entirely.
        scheduler = WorkflowScheduler(session_factory)
        scheduler._poll_once()
        assert len(svc.list_executions(wf.id)) == 0


class TestCalculateNextRun:
    def test_interval(self):
        trigger = WorkflowTrigger(
            workflow_id=uuid4(),
            trigger_type=TriggerType.SCHEDULE,
            configuration=json.dumps({"interval": 300}),
            next_run_at=None,
        )
        result = calculate_next_run(trigger)
        assert result is not None
        assert result > datetime.now(UTC)

    def test_event_returns_none(self):
        trigger = WorkflowTrigger(
            workflow_id=uuid4(),
            trigger_type=TriggerType.EVENT,
            configuration=json.dumps({"event_name": "x"}),
            next_run_at=None,
        )
        assert calculate_next_run(trigger) is None
