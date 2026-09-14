"""Tests for the orchestration execution worker.

Deterministic — the worker is exercised one poll at a time (not by spawning
its thread) so tests don't race, mirroring the workflow worker's tests. The
worker runs in-process by default off, so the synchronous ``/execute`` path
stays untouched; these tests drive the queue-claim + execute + recovery logic
directly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models.orchestration import Orchestration, OrchestrationStatus
from app.orchestration.worker import OrchestrationWorker


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, expire_on_commit=False)


def _make_queue_item(db, objective="queued work") -> Orchestration:
    """Create an orchestration in CREATED state (what the worker claims)."""
    orch = Orchestration(objective=objective, status=OrchestrationStatus.CREATED)
    db.add(orch)
    db.commit()
    db.refresh(orch)
    return orch


class TestOrchestrationWorkerClaim:
    def test_claim_moves_created_to_claimed(self, db, session_factory):
        orch = _make_queue_item(db)
        worker = OrchestrationWorker(session_factory)

        claimed = worker._claim_next(db)
        assert claimed == orch.id
        # A second claim finds nothing left ({status} was flipped by the first
        # claim, so the row is no longer visible to the queue).
        assert worker._claim_next(db) is None

    def test_claim_skips_non_created(self, db, session_factory):
        db.add(
            Orchestration(
                objective="already running",
                status=OrchestrationStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
        )
        db.commit()
        worker = OrchestrationWorker(session_factory)
        assert worker._claim_next(db) is None


class TestOrchestrationWorkerExecution:
    def test_poll_runs_a_queued_run_until_completed(self, db, session_factory):
        svc = _orchestration_service(db)
        from app.schemas.orchestration import OrchestrationCreate

        orch = svc.create(OrchestrationCreate(objective="single generic task"))

        # No agents -> the run still reaches a terminal status (engine handles
        # the empty workforce gracefully).
        worker = OrchestrationWorker(session_factory)
        worker._poll_once()

        db.refresh(orch)
        assert orch.status in (OrchestrationStatus.COMPLETED, OrchestrationStatus.FAILED)
        assert orch.completed_at is not None

    def test_worker_marks_thrown_error_as_failed(self, db, session_factory, monkeypatch):
        orch = _make_queue_item(db, "failing work")

        def boom(*_a, **_k):
            raise RuntimeError("kernel oops")

        monkeypatch.setattr("app.orchestration.worker.Orchestrator.execute", boom)
        worker = OrchestrationWorker(session_factory)
        worker._poll_once()

        db.refresh(orch)
        assert orch.status == OrchestrationStatus.FAILED
        assert "Worker error" in (orch.error or "")


class TestOrchestrationWorkerRecovery:
    def test_stale_active_run_is_recovered(self, db, session_factory):
        stale = datetime.now(UTC) - timedelta(seconds=7200)
        db.add(
            Orchestration(
                objective="crashed mid-run",
                status=OrchestrationStatus.RUNNING,
                started_at=stale,
            )
        )
        db.commit()

        worker = OrchestrationWorker(session_factory)
        worker.recover_stale()

        recovered = db.scalars(
            select(Orchestration).where(Orchestration.objective == "crashed mid-run")
        ).first()
        assert recovered.status == OrchestrationStatus.FAILED
        assert recovered.error == "Execution interrupted (recovered on startup)"

    def test_fresh_active_run_is_left_alone(self, db, session_factory):
        db.add(
            Orchestration(
                objective="young run",
                status=OrchestrationStatus.PLANNING,
                started_at=datetime.now(UTC),
            )
        )
        db.commit()
        OrchestrationWorker(session_factory).recover_stale()
        young = db.scalars(
            select(Orchestration).where(Orchestration.objective == "young run")
        ).first()
        assert young.status == OrchestrationStatus.PLANNING


def _orchestration_service(db):
    from app.services.orchestration_service import OrchestrationService

    return OrchestrationService(db)
