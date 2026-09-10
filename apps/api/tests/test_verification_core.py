"""Verification package tests (Phase 6).

Covers the shared verification abstraction: the six strategies, aggregation,
policies, and the service layer + persistence. Uses the ``db`` fixture for
SQLite-backed persistence checks.
"""

from __future__ import annotations

import pytest

from app.recovery.failure_injection import (
    MockAgentRunner,
    MockToolExecutor,
)
from app.verification.policy import VerificationPolicy
from app.verification.service import (
    VerificationService,
    to_dict,
)
from app.verification.strategies.deterministic import DefaultDeterministicVerifier
from app.verification.strategies.independent_agent import (
    DefaultIndependentAgentVerifier,
)
from app.verification.strategies.model import DefaultModelVerifier, MockModelEvaluator
from app.verification.strategies.rules import DefaultRuleVerifier, Rule
from app.verification.strategies.schema import DefaultSchemaVerifier
from app.verification.strategies.tool import DefaultToolVerifier
from app.verification.types import VerificationStatus

# ── Deterministic strategy ────────────────────────────────────────────────────


def test_deterministic_passes_all_checks():
    verifier = DefaultDeterministicVerifier()
    criteria = [
        {"key": "answer", "path": "answer", "expected": 4, "type": "equality"},
        {"key": "has_output", "path": "output", "type": "nonempty"},
        {"key": "name", "path": "name", "type": "presence"},
    ]
    outcome = verifier.verify({"answer": 4, "output": "done", "name": "x"}, criteria=criteria)
    assert outcome.status == VerificationStatus.PASS
    assert outcome.score == 1.0


def test_deterministic_fails_on_mismatch():
    verifier = DefaultDeterministicVerifier()
    criteria = [{"key": "answer", "path": "answer", "expected": 5, "type": "equality"}]
    outcome = verifier.verify({"answer": 4}, criteria=criteria)
    assert outcome.status == VerificationStatus.FAIL
    assert outcome.score == 0.0


def test_deterministic_partial():
    verifier = DefaultDeterministicVerifier()
    criteria = [
        {"key": "a", "path": "a", "expected": 1, "type": "equality"},
        {"key": "b", "path": "b", "expected": 2, "type": "equality"},
    ]
    outcome = verifier.verify({"a": 1, "b": 9}, criteria=criteria)
    assert outcome.status == VerificationStatus.PARTIAL
    assert outcome.score == 0.5


# ── Schema strategy ───────────────────────────────────────────────────────────


def test_schema_valid():
    verifier = DefaultSchemaVerifier()
    schema = {
        "type": "object",
        "required": ["name", "age"],
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    }
    outcome = verifier.verify(
        {"name": "Alice", "age": 30}, criteria=[{"type": "schema", "expected": schema}]
    )
    assert outcome.status == VerificationStatus.PASS


def test_schema_missing_required_field():
    verifier = DefaultSchemaVerifier()
    schema = {"required": ["name"], "properties": {"name": {"type": "string"}}}
    outcome = verifier.verify({"age": 30}, criteria=[{"type": "schema", "expected": schema}])
    assert outcome.status == VerificationStatus.FAIL


def test_schema_skipped_without_schema():
    verifier = DefaultSchemaVerifier()
    outcome = verifier.verify({"any": 1})
    assert outcome.status == VerificationStatus.SKIPPED


# ── Rules strategy ────────────────────────────────────────────────────────────


def test_rules_pass():
    verifier = DefaultRuleVerifier()
    rules = [
        {"key": "age", "path": "age", "type": "rule", "op": "gte", "expected": 18},
        {"key": "name", "path": "name", "type": "rule", "op": "nonempty"},
    ]
    outcome = verifier.verify({"age": 25, "name": "Bob"}, criteria=rules)
    assert outcome.status == VerificationStatus.PASS


def test_rules_fail_and_blocked_eval():
    verifier = DefaultRuleVerifier()
    rules = [
        {"key": "age", "path": "age", "type": "rule", "op": "lt", "expected": 18},
    ]
    outcome = verifier.verify({"age": 25}, criteria=rules)
    assert outcome.status == VerificationStatus.FAIL

    # Explicitly reject unsafe operators
    with pytest.raises(ValueError):
        Rule(field_path="x", op="eval", expected=[])


# ── Tool strategy ─────────────────────────────────────────────────────────────


def test_tool_verifier_reruns_tool():
    executor = MockToolExecutor(default_result={"status": "success", "output": "42"})
    verifier = DefaultToolVerifier()
    outcome = verifier.verify(
        {"answer": "42"},
        criteria=[{"type": "tool", "expected": "42"}],
        context={
            "tool_executor": executor,
            "tool_name": "calculator",
            "tool_args": {"expr": "6*7"},
            "agent_id": "agent-1",
        },
    )
    assert outcome.status == VerificationStatus.PASS


def test_tool_verifier_skipped_without_executor():
    verifier = DefaultToolVerifier()
    outcome = verifier.verify(
        {"answer": "42"},
        criteria=[{"type": "tool", "expected": "42"}],
        context={"tool_name": "calculator"},
    )
    assert outcome.status == VerificationStatus.SKIPPED


# ── Model strategy ───────────────────────────────────────────────────────────


def test_model_verifier_mock():
    provider = MockModelEvaluator()
    verifier = DefaultModelVerifier()
    outcome = verifier.verify(
        {"answer": 4}, criteria=[{"type": "model"}], context={"model_provider": provider}
    )
    # Mock passes when prompt contains a pass marker; otherwise fails deterministically
    assert outcome.status in (VerificationStatus.PASS, VerificationStatus.FAIL)
    assert 0.0 <= outcome.score <= 1.0


def test_model_verifier_skipped_without_provider():
    verifier = DefaultModelVerifier()
    outcome = verifier.verify({"answer": 4}, criteria=[{"type": "model"}], context={})
    assert outcome.status == VerificationStatus.SKIPPED


# ── Independent agent strategy ───────────────────────────────────────────────


def test_independent_agent_verifier():
    runner = MockAgentRunner(verifier_agent_id="fact-checker-1")
    verifier = DefaultIndependentAgentVerifier()
    outcome = verifier.verify(
        {"answer": 4},
        criteria=[{"type": "independent_agent"}],
        context={"agent_runner": runner, "producer_role": "researcher"},
    )
    assert outcome.status == VerificationStatus.PASS


def test_independent_agent_skipped_without_runner():
    verifier = DefaultIndependentAgentVerifier()
    outcome = verifier.verify({"answer": 4}, criteria=[{"type": "independent_agent"}], context={})
    assert outcome.status == VerificationStatus.SKIPPED


# ── Policy ───────────────────────────────────────────────────────────────────


def test_policy_validation_and_serialization():
    policy = VerificationPolicy(
        required=True,
        strategies=["deterministic", "schema"],
        minimum_score=0.8,
        minimum_confidence=0.7,
        max_attempts=3,
    )
    d = policy.to_dict()
    clone = VerificationPolicy.from_dict(d)
    assert clone.strategies == policy.strategies
    assert clone.minimum_score == 0.8

    with pytest.raises(ValueError):
        VerificationPolicy(strategies=["nonexistent"])


def test_policy_risk_gating():
    policy = VerificationPolicy(
        required=True,
        strategies=["deterministic", "schema", "rules", "tool", "model", "independent_agent"],
    )
    assert policy.select_strategies("low") == ["deterministic", "schema"]
    assert policy.select_strategies("medium") == ["deterministic", "schema", "rules", "tool"]
    assert policy.select_strategies("high") == [
        "deterministic",
        "schema",
        "rules",
        "tool",
        "model",
        "independent_agent",
    ]


# ── Service (with persistence) ────────────────────────────────────────────────


def test_service_verify_persists_and_aggregates(db):
    service = VerificationService(db)
    policy = VerificationPolicy(
        required=True, strategies=["deterministic", "schema"], minimum_score=0.5
    )
    criteria = [
        {"key": "answer", "path": "answer", "expected": 4, "type": "equality"},
        {
            "type": "schema",
            "key": "schema",
            "expected": {
                "required": ["answer"],
                "properties": {"answer": {"type": "integer"}},
            },
        },
    ]
    result = service.verify(
        {"answer": 4},
        policy=policy,
        execution_id=__import__("uuid").uuid4(),
        context={"criteria": criteria},
        risk_level="high",
    )

    assert result.status == VerificationStatus.PASS
    assert result.score == 1.0
    assert set(result.passed_criteria) >= {"answer", "schema"}

    # Persisted rows exist
    runs = service.list_runs()
    assert len(runs) == 1
    assert to_dict(runs[0])["status"] == "pass"


def test_service_skipped_when_not_required(db):
    service = VerificationService(db)
    policy = VerificationPolicy(required=False)
    result = service.verify({"any": 1}, policy=policy)
    assert result.status == VerificationStatus.SKIPPED


def test_service_unknown_strategy_raises():
    from app.verification.policy import VerificationPolicy

    with pytest.raises(ValueError):
        VerificationPolicy(strategies=["bad"])


def test_policy_crud(db):
    service = VerificationService(db)
    row = service.create_policy(
        name="test-policy",
        config={"required": True, "strategies": ["deterministic"]},
        scope_type="agent",
    )
    assert row.name == "test-policy"
    fetched = service.get_policy(row.id)
    assert fetched is not None
    policy = service.get_policy_for_scope("agent")
    assert policy.required is True
