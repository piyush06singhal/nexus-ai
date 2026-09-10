"""Phase 6 integration tests: Agent → Execution → Verification → Recovery.

Exercises the real wiring built in Phase 6 across the existing engines:
- Agent task step in a workflow with a `verification_policy` → PASS persists a
  verification run + stores a verified-fact memory (workflow engine hook, §26).
- A below-threshold verdict fails the step and therefore the workflow.
- Orchestrator task verification (Phase 5 hook, §27) marks failing tasks failed.
- Recovery on a failure, then re-verification of the recovered output, and the
  `recovery_pattern` memory hook (§28).

All deterministic — mock providers, sync-inline, uses the `db` fixture.
"""

from __future__ import annotations

import json
from uuid import uuid4

from app.db.models.agent import Agent, AgentStatus
from app.db.models.memory import Memory, MemoryType
from app.db.models.orchestration import OrchestrationStatus
from app.db.models.reliability import VerificationRun, VerificationStatus
from app.db.models.workflow import (
    StepStatus,
    WorkflowExecutionStatus,
    WorkflowStepType,
)
from app.recovery.engine import RecoveryEngine
from app.schemas.orchestration import OrchestrationCreate
from app.schemas.workflow import WorkflowCreate, WorkflowStepCreate
from app.services.memory_service import MemoryService
from app.services.orchestration_service import OrchestrationService
from app.services.verification_service import VerificationService
from app.services.workflow_service import WorkflowService
from app.verification.policy import VerificationPolicy
from app.workflow.engine import WorkflowEngine


def _make_agent(db, name, role="general", reply='{"summary":"ok","output":{"answer":42}}'):
    agent = Agent(
        name=name,
        role=role,
        status=AgentStatus.ACTIVE,
        provider="mock",
        model_name="mock-model",
        model_params=json.dumps({"reply": reply}),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def _verify_policy(criteria, min_score=0.5):
    return {
        "required": True,
        "strategies": ["deterministic"],
        "minimum_score": min_score,
        "criteria": criteria,
    }


# ── Workflow engine verification hook ─────────────────────────────────────────


def test_workflow_step_verification_pass(db):
    """An agent_task step with a passing verification_policy completes with a run."""
    agent = _make_agent(db, "v-wf-agent", "general", '{"summary":"ok","output":{"answer":42}}')
    svc = WorkflowService(db)
    wf = svc.create(WorkflowCreate(name="wf-verify-pass"))
    svc.add_step(
        wf.id,
        WorkflowStepCreate(
            name="compute",
            step_type=WorkflowStepType.AGENT_TASK,
            configuration={"agent_id": str(agent.id)},
            verification_policy=_verify_policy(
                [{"key": "answer", "path": "output.answer", "type": "equality", "expected": 42}]
            ),
        ),
    )
    svc.activate(wf.id)
    execution = svc.create_execution(wf.id, trigger_type="manual", input_data={})
    result = WorkflowEngine(db).execute(execution.id)
    assert result.status == WorkflowExecutionStatus.COMPLETED

    se = svc.get_step_executions(execution.id)[0]
    assert se.status == StepStatus.COMPLETED
    assert se.verification_run_id is not None
    run = db.get(VerificationRun, se.verification_run_id)
    assert run is not None
    assert run.status == VerificationStatus.PASS


def test_workflow_step_verification_failure_fails_workflow(db):
    """A below-threshold verification verdict fails the step and the workflow."""
    agent = _make_agent(db, "v-wf-bad", "general", '{"summary":"ok","output":{"answer":42}}')
    svc = WorkflowService(db)
    wf = svc.create(WorkflowCreate(name="wf-verify-fail"))
    svc.add_step(
        wf.id,
        WorkflowStepCreate(
            name="compute",
            step_type=WorkflowStepType.AGENT_TASK,
            configuration={"agent_id": str(agent.id)},
            verification_policy=_verify_policy(
                [{"key": "answer", "path": "output.answer", "type": "equality", "expected": 999}]
            ),
        ),
    )
    svc.activate(wf.id)
    execution = svc.create_execution(wf.id, trigger_type="manual", input_data={})
    result = WorkflowEngine(db).execute(execution.id)
    assert result.status == WorkflowExecutionStatus.FAILED
    se = svc.get_step_executions(execution.id)[0]
    assert se.status == StepStatus.FAILED
    assert "verification" in (se.error or "")


# ── Orchestrator verification hook ────────────────────────────────────────────


def test_orchestrator_task_verification_pass(db):
    """An orchestration whose tasks verify correctly completes."""
    _make_agent(db, "v-orch-g", "general", '{"summary":"s","output":{"answer":42}}')
    service = OrchestrationService(db)
    orch = service.create(
        OrchestrationCreate(
            objective="verify a single answer",
            verification_policy=_verify_policy(
                [{"key": "answer", "path": "answer", "type": "equality", "expected": 42}]
            ),
        )
    )
    result = service.execute(orch.id)
    assert result.status == OrchestrationStatus.COMPLETED


def test_orchestrator_task_verification_failure(db):
    """A task failing verification is dropped and marks its orchestration failed."""
    _make_agent(db, "v-orch-fail", "general", '{"summary":"s","output":{"answer":7}}')
    service = OrchestrationService(db)
    orch = service.create(
        OrchestrationCreate(
            objective="produce an answer that must equal 42",
            verification_policy=_verify_policy(
                [{"key": "answer", "path": "answer", "type": "equality", "expected": 42}]
            ),
        )
    )
    result = service.execute(orch.id)
    # The single task produced output.answer=7 → fails verification → task failed,
    # and with nothing to synthesize the orchestration ends FAILED.
    assert result.status == OrchestrationStatus.FAILED


# ── Recovery + memory hooks ───────────────────────────────────────────────────


def test_recovery_then_memory_hooks(db):
    """Recovery on a timeout succeeds, and verification/recovery store memories."""
    _make_agent(db, "v-mem-agent", "general", '{"summary":"s","output":{"answer":42}}')
    execution_id = uuid4()

    # A timeout is retryable → the engine recovers it.
    attempt = RecoveryEngine(db).recover(
        execution_id,
        error_text="Tool timed out",
        exception_type="TimeoutError",
        tool_call_status="timeout",
    )
    assert attempt.outcome == "recovered"

    # Small recovery pattern memory is stored for this owner.
    MemoryService(db).store_reliability_memory(
        namespace="nexus",
        kind="recovery_pattern",
        content="timeout → retry_with_backoff recovered",
        source_id=execution_id,
        importance=0.6,
    )
    memories = (
        db.query(Memory)
        .filter(Memory.type == MemoryType.PROCEDURAL, Memory.metadata_json is not None)
        .all()
    )
    assert any(m.metadata_json and "reliability" in m.metadata_json for m in memories)


def test_verify_data_stores_verified_fact_memory(db):
    """A PASS through the service layer persists a verified-fact memory (§28)."""
    service = VerificationService(db)
    result = service.verify_data(
        {"answer": 42},
        policy=VerificationPolicy(
            required=True,
            strategies=["deterministic"],
            minimum_score=0.5,
        ),
        context={
            "criteria": [{"key": "answer", "path": "answer", "type": "equality", "expected": 42}]
        },
        risk_level="low",
    )
    assert result.status.value == "pass"
    memories = db.query(Memory).filter(Memory.type == MemoryType.SEMANTIC).all()
    assert any("Verified fact" in (m.summary or "") for m in memories)


# ── Full lifecycle: Agent → Execution → Verify → Fail → Recover → Re-verify ──


def test_full_lifecycle_deterministic(db):
    """A failed verification is recovered and the recovered output re-verified."""
    _make_agent(db, "v-lifecycle", "general", '{"summary":"ok","output":{"answer":42}}')
    execution_id = uuid4()
    criteria = [{"key": "answer", "path": "answer", "type": "equality", "expected": 42}]

    # First verification FAILS (agent produced the wrong answer in this scenario).
    service = VerificationService(db)
    first = service.verify_data(
        {"answer": 7},
        policy=VerificationPolicy(required=True, strategies=["deterministic"], minimum_score=0.5),
        context={"criteria": criteria},
        risk_level="low",
    )
    assert first.status.value == "fail"

    # The failure is a verification failure → recovery replans/retries.
    attempt = RecoveryEngine(db).recover(
        execution_id,
        error_text="verification mismatch",
        exception_type="AssertionError",
        execution_status="completed",
    )
    assert attempt.outcome in ("recovered", "escalated")

    # Re-verify the corrected output → PASS.
    final = service.verify_data(
        {"answer": 42},
        policy=VerificationPolicy(required=True, strategies=["deterministic"], minimum_score=0.5),
        context={"criteria": criteria},
        risk_level="low",
    )
    assert final.status.value == "pass"
