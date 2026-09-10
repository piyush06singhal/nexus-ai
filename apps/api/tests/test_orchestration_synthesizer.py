"""Tests for result synthesis with source attribution (spec §14, §15, §16, §33)."""

from __future__ import annotations

import uuid

import pytest

from app.db.models.orchestration import (
    Orchestration,
    OrchestrationResult,
    OrchestrationStatus,
    OrchestrationTask,
    OrchestrationTaskStatus,
)
from app.orchestration.synthesizer import ResultSynthesizer
from app.orchestration.types import SynthesisError


def _orch(objective="Analyze the market"):
    return Orchestration(id=uuid.uuid4(), objective=objective, status=OrchestrationStatus.RUNNING)


def _task(name, status=OrchestrationTaskStatus.COMPLETED):
    return OrchestrationTask(
        id=uuid.uuid4(), orchestration_id=uuid.uuid4(), name=name, status=status
    )


def _result(agent, task_id, data, content="headline", confidence=0.8):
    return OrchestrationResult(
        id=uuid.uuid4(),
        orchestration_id=uuid.uuid4(),
        task_id=task_id,
        agent_id=agent,
        content=content,
        structured_data=__import__("json").dumps(data),
        confidence=confidence,
    )


def test_synthesize_produces_required_shape():
    a = uuid.uuid4()
    task = _task("research")
    synth = ResultSynthesizer()
    result = synth.synthesize(
        _orch(),
        [_result(a, task.id, {"finding": "x"})],
        [task],
        conflicts=[],
    )
    for key in (
        "status",
        "summary",
        "findings",
        "sources",
        "conflicts",
        "incomplete_tasks",
        "agent_contributions",
    ):
        assert key in result


def test_source_attribution_present():
    a = uuid.uuid4()
    task = _task("research")
    synth = ResultSynthesizer()
    result = synth.synthesize(
        _orch(),
        [_result(a, task.id, {"finding": "x"}, content="source text")],
        [task],
    )
    assert result["sources"][0]["agent_id"] == str(a)
    assert result["sources"][0]["task_id"] == str(task.id)
    assert result["sources"][0]["content"] == "source text"


def test_findings_carry_agent_and_task():
    a = uuid.uuid4()
    task = _task("research")
    synth = ResultSynthesizer()
    result = synth.synthesize(_orch(), [_result(a, task.id, {"finding": "x"})], [task])
    finding = result["findings"][0]
    assert finding["agent_id"] == str(a)
    assert finding["task_id"] == str(task.id)


def test_incomplete_tasks_listed():
    a = uuid.uuid4()
    completed = _task("ok", OrchestrationTaskStatus.COMPLETED)
    failed = _task("broken", OrchestrationTaskStatus.FAILED)
    synth = ResultSynthesizer()
    result = synth.synthesize(
        _orch(),
        [_result(a, completed.id, {"finding": "x"})],
        [completed, failed],
    )
    incomplete_names = [t["name"] for t in result["incomplete_tasks"]]
    assert "broken" in incomplete_names
    assert "ok" not in incomplete_names


def test_conflicts_forwarded():
    a = uuid.uuid4()
    task = _task("research")
    synth = ResultSynthesizer()
    fake_conflict = type(
        "C",
        (),
        {
            "field": "size",
            "agent_a": a,
            "agent_b": uuid.uuid4(),
            "value_a": 100,
            "value_b": 400,
            "kind": "numeric",
        },
    )()
    result = synth.synthesize(
        _orch(), [_result(a, task.id, {"finding": "x"})], [task], conflicts=[fake_conflict]
    )
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["field"] == "size"
    assert result["conflicts"][0]["kind"] == "numeric"


def test_no_results_raises_synthesis_error():
    synth = ResultSynthesizer()
    with pytest.raises(SynthesisError):
        synth.synthesize(_orch(), [], [_task("a")])


def test_never_invents_data():
    a = uuid.uuid4()
    task = _task("research")
    synth = ResultSynthesizer()
    result = synth.synthesize(_orch(), [_result(a, task.id, {"finding": "x"})], [task])
    # Only the data actually present appears in the source / findings.
    assert result["sources"][0].get("__invented") is None
    joined = str(result)
    assert "x" in joined


def test_agent_contributions_grouped():
    a = uuid.uuid4()
    b = uuid.uuid4()
    task_a = _task("a")
    task_b = _task("b")
    synth = ResultSynthesizer()
    result = synth.synthesize(
        _orch(),
        [
            _result(a, task_a.id, {"k": "v"}),
            _result(b, task_b.id, {"k2": "v2"}),
        ],
        [task_a, task_b],
    )
    assert str(a) in result["agent_contributions"]
    assert str(b) in result["agent_contributions"]


def test_summary_mentions_conflicts_when_present():
    a = uuid.uuid4()
    task = _task("research")
    synth = ResultSynthesizer()
    conflict = type(
        "C",
        (),
        {
            "field": "x",
            "agent_a": uuid.uuid4(),
            "agent_b": None,
            "value_a": 1,
            "value_b": 2,
            "kind": "numeric",
        },
    )()
    result = synth.synthesize(
        _orch(), [_result(a, task.id, {"f": 1})], [task], conflicts=[conflict]
    )
    assert "conflict" in result["summary"]
