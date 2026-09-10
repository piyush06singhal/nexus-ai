"""Self-Healing Research Workflow (Phase 6 demo, spec §51).

A deterministic, persisted end-to-end demonstration of the reliability layer:
a research tool call fails (failure injection) → the failure is diagnosed →
a bounded recovery strategy (retry with fallback) recovers it → the final
research result is independently verified → PASS.

Everything runs sync-inline against SQLite with mock providers so the demo is
repeatable in CI with no paid API.
"""

from __future__ import annotations

import json
from uuid import uuid4

from app.db.models.agent import Agent, AgentStatus
from app.db.models.reliability import FailureDiagnosis, RecoveryPlan, VerificationRun
from app.recovery.engine import RecoveryEngine
from app.recovery.failure_injection import (
    FailInjectionSpec,
    InjectionKind,
    MockToolExecutor,
)
from app.services.verification_service import VerificationService
from app.verification.policy import VerificationPolicy


def test_self_healing_research_workflow(db):
    # 1. A research agent exists and produced a result.
    agent = Agent(
        name="self-healing-researcher",
        role="researcher",
        status=AgentStatus.ACTIVE,
        provider="mock",
        model_name="mock-model",
        model_params=json.dumps(
            {"reply": '{"summary":"market analysis","output":{"market":"growth","confidence":0.9}}'}
        ),
    )
    db.add(agent)
    db.commit()

    execution_id = uuid4()

    # 2. The research tool call fails (timeout) via deterministic failure injection.
    tool = MockToolExecutor(
        spec=FailInjectionSpec(kind=InjectionKind.TOOL, error_message="research api down")
    )
    result = tool(tool_name="research", args={"query": "market"})
    assert result["status"] == "error"

    # 3. The failure is diagnosed and recovered.
    engine = RecoveryEngine(db)
    attempt = engine.recover(
        execution_id,
        error_text=result.get("error", "research api down"),
        exception_type="RuntimeError",
        tool_call_status="error",
        context={"tool_name": "research"},
    )
    assert attempt.outcome == "recovered"

    # The diagnosis and plan are persisted and observable.
    assert db.query(FailureDiagnosis).filter_by(execution_id=execution_id).count() == 1
    assert db.query(RecoveryPlan).filter_by(execution_id=execution_id).count() == 1

    # 4. The final research result is independently verified → PASS.
    verification = VerificationService(db).verify_data(
        {"market": "growth", "confidence": 0.9},
        policy=VerificationPolicy(required=True, strategies=["deterministic"], minimum_score=0.5),
        context={
            "criteria": [
                {"key": "market", "path": "market", "type": "presence"},
                {"key": "confidence", "path": "confidence", "type": "nonempty"},
            ]
        },
        risk_level="low",
    )
    assert verification.status.value == "pass"

    # Persisted, observable verification run.
    run = db.query(VerificationRun).order_by(VerificationRun.created_at.desc()).first()
    assert run is not None
    assert run.status.value == "pass"
