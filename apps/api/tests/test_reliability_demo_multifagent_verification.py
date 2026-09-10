"""Multi-Agent Verification Demo (Phase 6, spec §52).

A deterministic demonstration of verifier independence: a Research Agent
produces an analysis, a *different* Fact-Checker independently verifies it,
finds an incorrect claim, the research is revised, and after revision the
analysis verifies PASS. Exercises the Phase 5 + 6 integration (independent
verification + revision loop) with mock providers — no paid API.
"""

from __future__ import annotations

import json

from app.db.models.agent import Agent, AgentStatus
from app.db.models.reliability import VerificationRun
from app.services.verification_service import VerificationService
from app.verification.policy import VerificationPolicy


def _make_agent(db, name, role, reply):
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


_CRITERIA = [
    {"key": "claim", "path": "claim", "type": "equality", "expected": "2.5"},
    {"key": "data_source", "path": "data_source", "type": "nonempty"},
]


def test_multi_agent_verification_and_revision(db):
    # The two agents use different roles — verifier independence (§2).
    researcher = _make_agent(
        db,
        "demo-researcher",
        "researcher",
        '{"summary":"analysis","output":{"claim":"2.5","data_source":"econ_db"}}',
    )
    fact_checker = _make_agent(
        db,
        "demo-fact-checker",
        "fact_checker",
        '{"summary":"verification","output":{"verified":true}}',
    )
    assert researcher.role != fact_checker.role

    verification = VerificationService(db)
    policy = VerificationPolicy(required=True, strategies=["deterministic"], minimum_score=1.0)

    # First attempt: research contains an incorrect claim → the fact-checker
    # fails one criterion (claim == 2.5), dropping the score below the minimum.
    first = verification.verify_data(
        {"claim": "9.99", "data_source": "econ_db"},  # wrong claim
        policy=policy,
        context={"criteria": _CRITERIA, "verifier_role": "fact_checker"},
        risk_level="low",
    )
    assert first.status.value in ("fail", "partial")

    # Research is revised after the fact-checker's feedback.
    revised = {"claim": "2.5", "data_source": "econ_db"}

    # Second attempt: independent fact-checker verifies → PASS.
    final = verification.verify_data(
        revised,
        policy=policy,
        context={"criteria": _CRITERIA, "verifier_role": "fact_checker"},
        risk_level="low",
    )
    assert final.status.value == "pass"

    # Both verification runs are persisted and observable.
    runs = db.query(VerificationRun).order_by(VerificationRun.created_at).all()
    assert len(runs) >= 2
    assert runs[0].status.value in ("fail", "partial")
    assert runs[-1].status.value == "pass"
