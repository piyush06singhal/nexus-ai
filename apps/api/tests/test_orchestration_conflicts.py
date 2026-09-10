"""Tests for conflict detection (spec §13, §33)."""

from __future__ import annotations

import uuid

from app.db.models.orchestration import OrchestrationResult
from app.orchestration.conflicts import NumericConflictDetector


def _result(agent, data, confidence=0.9):
    return OrchestrationResult(
        id=uuid.uuid4(),
        orchestration_id=uuid.uuid4(),
        agent_id=uuid.UUID(agent) if isinstance(agent, str) else agent,
        structured_data=__import__("json").dumps(data),
        confidence=confidence,
    )


def test_no_conflict_when_values_agree():
    a = uuid.uuid4()
    b = uuid.uuid4()
    detector = NumericConflictDetector(threshold=0.2)
    conflicts = detector.detect([_result(str(a), {"share": 0.5}), _result(str(b), {"share": 0.51})])
    assert conflicts == []


def test_numeric_conflict_above_threshold():
    a = uuid.uuid4()
    b = uuid.uuid4()
    detector = NumericConflictDetector(threshold=0.2)
    conflicts = detector.detect(
        [_result(str(a), {"market_size": 100}), _result(str(b), {"market_size": 500})]
    )
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.field == "market_size"
    assert c.kind == "numeric"
    assert c.value_a == 100
    assert c.value_b == 500


def test_boolean_contradiction_detected():
    a = uuid.uuid4()
    b = uuid.uuid4()
    detector = NumericConflictDetector(threshold=0.2)
    conflicts = detector.detect(
        [_result(str(a), {"compliant": True}), _result(str(b), {"compliant": False})]
    )
    assert len(conflicts) == 1
    assert conflicts[0].kind == "boolean"


def test_small_numeric_diff_below_threshold_not_conflict():
    a = uuid.uuid4()
    b = uuid.uuid4()
    detector = NumericConflictDetector(threshold=0.2)
    conflicts = detector.detect(
        [_result(str(a), {"growth": 8.0}), _result(str(b), {"growth": 8.2})]
    )
    assert conflicts == []


def test_zero_division_does_not_crash():
    a = uuid.uuid4()
    b = uuid.uuid4()
    detector = NumericConflictDetector(threshold=0.2)
    conflicts = detector.detect([_result(str(a), {"count": 0}), _result(str(b), {"count": 0})])
    assert conflicts == []


def test_malformed_result_is_tolerated():
    a = uuid.uuid4()
    b = uuid.uuid4()
    detector = NumericConflictDetector(threshold=0.2)
    bad = OrchestrationResult(
        id=uuid.uuid4(), orchestration_id=uuid.uuid4(), agent_id=a, structured_data="not-json"
    )
    conflicts = detector.detect([bad, _result(str(b), {"x": 1, "y": 2})])
    assert conflicts == []


def test_detection_is_deterministic():
    a = uuid.uuid4()
    b = uuid.uuid4()
    detector = NumericConflictDetector(threshold=0.1)
    results = [
        _result(str(a), {"z": 5, "w": 100}),
        _result(str(b), {"w": 400, "z": 9}),
    ]
    first = detector.detect(results)
    second = detector.detect(results)
    assert [(c.field, str(c.agent_a)) for c in first] == [(c.field, str(c.agent_a)) for c in second]
