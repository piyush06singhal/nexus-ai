"""Tests for the workflow condition evaluator and path resolution.

These are pure-logic tests — no DB, no HTTP.
"""

import pytest

from app.workflow.conditions import (
    ConditionEvaluationError,
    evaluate_condition,
    resolve_path,
)

SAMPLE_STATE = {
    "input": {"topic": "AI", "region": "US", "lead_count": 75},
    "steps": {
        "research": {"output": {"lead_count": 75, "summary": "strong"}, "status": "completed"},
        "analysis": {"output": {"score": 0.9, "tags": ["ai", "ml"]}, "status": "completed"},
    },
}


class TestResolvePath:
    def test_top_level_input(self):
        assert resolve_path(SAMPLE_STATE, "input.topic") == "AI"

    def test_step_output(self):
        assert resolve_path(SAMPLE_STATE, "steps.research.output.lead_count") == 75

    def test_missing_path_raises(self):
        with pytest.raises(ConditionEvaluationError):
            resolve_path(SAMPLE_STATE, "steps.ghost.output.x")

    def test_missing_key_raises(self):
        with pytest.raises(ConditionEvaluationError):
            resolve_path(SAMPLE_STATE, "input.nonexistent")

    def test_empty_path_raises(self):
        with pytest.raises(ConditionEvaluationError):
            resolve_path(SAMPLE_STATE, "")


class TestCompareOperators:
    def test_equal(self):
        assert evaluate_condition(
            {"field": "steps.research.output.lead_count", "op": "eq", "value": 75},
            SAMPLE_STATE,
        )

    def test_not_equal(self):
        assert evaluate_condition(
            {"field": "steps.research.output.lead_count", "op": "ne", "value": 10},
            SAMPLE_STATE,
        )

    def test_greater_than(self):
        assert evaluate_condition(
            {"field": "steps.research.output.lead_count", "op": "gt", "value": 50},
            SAMPLE_STATE,
        )

    def test_greater_than_false(self):
        assert not evaluate_condition(
            {"field": "steps.research.output.lead_count", "op": "gt", "value": 100},
            SAMPLE_STATE,
        )

    def test_less_than_or_equal(self):
        assert evaluate_condition(
            {"field": "input.lead_count", "op": "lte", "value": 75},
            SAMPLE_STATE,
        )

    def test_contains_string(self):
        assert evaluate_condition(
            {"field": "steps.research.output.summary", "op": "contains", "value": "rong"},
            SAMPLE_STATE,
        )

    def test_contains_list(self):
        assert evaluate_condition(
            {"field": "steps.analysis.output.tags", "op": "contains", "value": "ai"},
            SAMPLE_STATE,
        )

    def test_not_contains(self):
        assert evaluate_condition(
            {"field": "steps.analysis.output.tags", "op": "not_contains", "value": "finance"},
            SAMPLE_STATE,
        )

    def test_invalid_operator_raises(self):
        with pytest.raises(ConditionEvaluationError):
            evaluate_condition(
                {"field": "input.topic", "op": "typo_operator", "value": "x"},
                SAMPLE_STATE,
            )


class TestLogicalConditions:
    def test_all(self):
        cond = {
            "and": [
                {"field": "steps.research.output.lead_count", "op": "gt", "value": 50},
                {"field": "input.region", "op": "eq", "value": "US"},
            ]
        }
        assert evaluate_condition(cond, SAMPLE_STATE)

    def test_any(self):
        cond = {
            "or": [
                {"field": "steps.research.output.lead_count", "op": "lt", "value": 10},
                {"field": "input.region", "op": "eq", "value": "US"},
            ]
        }
        assert evaluate_condition(cond, SAMPLE_STATE)

    def test_nested_and_or(self):
        cond = {
            "and": [
                {"field": "steps.research.output.lead_count", "op": "gt", "value": 50},
                {
                    "or": [
                        {"field": "input.region", "op": "eq", "value": "EU"},
                        {"field": "input.topic", "op": "eq", "value": "AI"},
                    ]
                },
            ]
        }
        assert evaluate_condition(cond, SAMPLE_STATE)

    def test_and_false(self):
        cond = {
            "and": [
                {"field": "steps.research.output.lead_count", "op": "gt", "value": 50},
                {"field": "input.region", "op": "eq", "value": "EU"},
            ]
        }
        assert not evaluate_condition(cond, SAMPLE_STATE)

    def test_empty_condition_passes(self):
        assert evaluate_condition({}, SAMPLE_STATE)

    def test_malformed_raises(self):
        with pytest.raises(ConditionEvaluationError):
            evaluate_condition({"unrecognized": True}, SAMPLE_STATE)
