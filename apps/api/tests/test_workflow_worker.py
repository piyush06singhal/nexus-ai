"""Tests for the workflow worker and the DB-backed queue.

Deterministic — the worker is exercised one poll at a time (not by spawning
its thread) so tests don't race.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models.agent import AgentStatus
from app.db.models.workflow import WorkflowExecutionStatus, WorkflowStepType
from app.schemas.agent import AgentCreate
from app.schemas.workflow import WorkflowCreate, WorkflowStepCreate
from app.services.agent_service import AgentService
from app.services.workflow_service import WorkflowService
from app.workflow.queue import WorkflowQueue
from app.workflow.worker import WorkflowWorker


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, expire_on_commit=False)


def _make_active_delay_wf(svc, db, name):
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


class TestWorkflowQueue:
    def test_claim_returns_first_queued(self, db):
        svc = WorkflowService(db)
        wf = _make_active_delay_wf(svc, db, "q-wf")
        e1 = svc.create_execution(wf.id, trigger_type="manual")
        e2 = svc.create_execution(wf.id, trigger_type="manual")

        queue = WorkflowQueue(db)
        first = queue.claim_next()
        assert first == e1.id
        # Second claim returns the other queued execution.
        second = queue.claim_next()
        assert second == e2.id
        # Nothing left.
        assert queue.claim_next() is None

    def test_claim_does_not_return_claimed_twice(self, db):
        svc = WorkflowService(db)
        wf = _make_active_delay_wf(svc, db, "q-wf2")
        execution = svc.create_execution(wf.id, trigger_type="manual")

        queue = WorkflowQueue(db)
        assert queue.claim_next() == execution.id
        assert queue.claim_next() is None


class TestWorkflowWorker:
    def test_worker_runs_execution(self, db, session_factory):
        svc = WorkflowService(db)
        wf = _make_active_delay_wf(svc, db, "worker-wf")
        execution = svc.create_execution(wf.id, trigger_type="manual")

        worker = WorkflowWorker(session_factory)
        worker._poll_once()

        db.refresh(execution)
        assert execution.status == WorkflowExecutionStatus.COMPLETED

    def test_worker_recovery(self, db, session_factory):
        svc = WorkflowService(db)
        wf = _make_active_delay_wf(svc, db, "worker-recovery")
        execution = svc.create_execution(wf.id, trigger_type="manual")
        # Simulate a crash: mark it running with an old started_at.
        execution.status = WorkflowExecutionStatus.RUNNING
        execution.started_at = datetime.now(UTC) - timedelta(hours=10)
        db.commit()

        worker = WorkflowWorker(session_factory)
        worker.recover_stale()

        db.refresh(execution)
        assert execution.status == WorkflowExecutionStatus.TIMED_OUT

    def test_worker_agent_step_completes(self, db, session_factory):
        """A worker running an agent-task workflow completes end-to-end."""
        svc = WorkflowService(db)
        agent = AgentService(db).create(
            AgentCreate(
                name="worker-agent",
                status=AgentStatus.ACTIVE,
                provider="mock",
                model_name="mock-model",
            )
        )
        wf = svc.create(WorkflowCreate(name="worker-agent-wf"))
        svc.add_step(
            wf.id,
            WorkflowStepCreate(
                name="research",
                step_type=WorkflowStepType.AGENT_TASK,
                configuration={"agent_id": str(agent.id), "input_mapping": {}},
            ),
        )
        svc.activate(wf.id)
        execution = svc.create_execution(wf.id, trigger_type="manual")

        worker = WorkflowWorker(session_factory)
        worker._poll_once()

        db.refresh(execution)
        assert execution.status == WorkflowExecutionStatus.COMPLETED
        step_execs = svc.get_step_executions(execution.id)
        assert len(step_execs) == 1
