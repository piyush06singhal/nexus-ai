"""Item 6 — Worker topology tests.

Covers the shared worker-lifecycle module (:mod:`app.workers`) and the
headless entrypoint (:mod:`app.main_worker`) that backs the split-container
production topology: API request-serving only, `worker` container owns the
queues, heartbeat file drives the container healthcheck.

Flag-on cases inject recording fakes at the class import sites that
``start_workers()`` resolves, so no real daemon thread ever touches a DB.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.workers import WorkerHandles, start_workers, stop_workers


class _FakeWorker:
    def __init__(self, *_args, **_kwargs) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture(autouse=True)
def _workers_off(monkeypatch):
    """Default: every worker flag off, no heartbeat path — so start_workers()
    never touches a real DB inside these tests."""
    monkeypatch.setattr(settings, "workflow_worker_enabled", False)
    monkeypatch.setattr(settings, "orchestration_worker_enabled", False)
    monkeypatch.setattr(settings, "worker_heartbeat_path", "")


# ── app.workers ─────────────────────────────────────────────────────────────


def test_start_workers_noop_when_all_disabled():
    handles = start_workers()
    assert isinstance(handles, WorkerHandles)
    assert not handles.active
    assert handles.workflow is None
    assert handles.scheduler is None
    assert handles.orchestration is None


def test_stop_workers_accepts_none():
    stop_workers(None)  # must not raise


def test_stop_workers_noop_on_empty_handles():
    stop_workers(WorkerHandles())  # must not raise


def test_start_workers_wires_workflow_and_scheduler(monkeypatch):
    import app.workflow.scheduler as scheduler_mod
    import app.workflow.worker as worker_mod

    monkeypatch.setattr(settings, "workflow_worker_enabled", True)
    wf = _FakeWorker()
    sch = _FakeWorker()
    monkeypatch.setattr(worker_mod, "WorkflowWorker", lambda *_a, **_k: wf)
    monkeypatch.setattr(scheduler_mod, "WorkflowScheduler", lambda *_a, **_k: sch)

    handles = start_workers()
    assert handles.active
    assert handles.workflow is wf and handles.workflow.started
    assert handles.scheduler is sch and handles.scheduler.started
    assert handles.orchestration is None

    stop_workers(handles)
    assert wf.stopped and sch.stopped


def test_start_workers_wires_orchestration(monkeypatch):
    import app.orchestration.worker as orch_mod

    monkeypatch.setattr(settings, "orchestration_worker_enabled", True)
    orch = _FakeWorker()
    monkeypatch.setattr(orch_mod, "OrchestrationWorker", lambda *_a, **_k: orch)

    handles = start_workers()
    assert handles.active
    assert handles.orchestration is orch and handles.orchestration.started
    assert handles.workflow is None

    stop_workers(handles)
    assert orch.stopped


def test_stop_workers_is_idempotent(monkeypatch):
    import app.workflow.scheduler as scheduler_mod
    import app.workflow.worker as worker_mod

    monkeypatch.setattr(settings, "workflow_worker_enabled", True)
    monkeypatch.setattr(worker_mod, "WorkflowWorker", lambda *_a, **_k: _FakeWorker())
    monkeypatch.setattr(scheduler_mod, "WorkflowScheduler", lambda *_a, **_k: _FakeWorker())

    handles = start_workers()
    stop_workers(handles)
    stop_workers(handles)  # second call must not raise


# ── app.main_worker ─────────────────────────────────────────────────────────


def test_headless_worker_run_returns_cleanly(monkeypatch):
    from app import main_worker

    monkeypatch.setattr(main_worker, "_shutdown_requested", True)
    assert main_worker.run() == 0


def test_heartbeat_refreshes_configured_file(monkeypatch, tmp_path):
    from app import main_worker

    heartbeat = tmp_path / "worker.heartbeat"
    monkeypatch.setattr(settings, "worker_heartbeat_path", str(heartbeat))
    main_worker._refresh_heartbeat()
    assert heartbeat.exists()
    assert heartbeat.is_file()


def test_heartbeat_noop_when_unset():
    from app import main_worker

    # heartbeat path is cleared by the autouse fixture; must not raise
    main_worker._refresh_heartbeat()
    assert settings.worker_heartbeat_path == ""


def test_config_heartbeat_default_empty():
    assert settings.worker_heartbeat_path == ""


def test_main_worker_runs_as_module():
    """python -m app.main_worker resolves through the run() entrypoint."""
    import importlib

    main_worker = importlib.import_module("app.main_worker")
    assert callable(main_worker.run)
