"""Deterministic evaluation dataset (Phase 6, spec §34).

Eight canonical test cases covering simple reasoning, structured JSON
generation, tool selection, tool-failure recovery, multi-agent collaboration,
verification failure, retry, and partial completion. Each case has a
mock-provider fixture — no paid API required.
"""

from __future__ import annotations

from uuid import uuid4

from app.evaluation.entities import Evaluation, EvaluationCase, EvaluationTarget


def build_default_dataset() -> Evaluation:
    """Build the default deterministic evaluation dataset (§34)."""
    return Evaluation(
        id=uuid4(),
        name="NEXUS Default Evaluation Suite",
        target_type=EvaluationTarget.SYSTEM,
        description="Eight canonical cases covering core NEXUS capabilities.",
        cases=[
            _case_simple_reasoning(),
            _case_structured_json(),
            _case_tool_selection(),
            _case_tool_failure_recovery(),
            _case_multi_agent_collaboration(),
            _case_verification_failure(),
            _case_retry(),
            _case_partial_completion(),
        ],
    )


def _case_simple_reasoning() -> EvaluationCase:
    """Case 1: Simple reasoning task."""
    return EvaluationCase(
        id=uuid4(),
        name="Simple Reasoning",
        input={"task": "What is 2 + 2?", "context": "basic arithmetic"},
        expected_outcome={"answer": 4, "method": "arithmetic"},
        criteria=[
            {"key": "answer", "type": "equality", "expected": 4},
            {"key": "method", "type": "eq", "expected": "arithmetic"},
        ],
    )


def _case_structured_json() -> EvaluationCase:
    """Case 2: Structured JSON generation."""
    return EvaluationCase(
        id=uuid4(),
        name="Structured JSON Generation",
        input={"task": "Generate a user profile", "schema": {"name": "string", "age": "integer"}},
        expected_outcome={
            "name": "test_user",
            "age": 30,
            "email": "test@example.com",
        },
        criteria=[
            {"key": "name", "type": "type_check", "expected": "string"},
            {"key": "age", "type": "type_check", "expected": "integer"},
            {"key": "email", "type": "contains", "expected": "@"},
        ],
    )


def _case_tool_selection() -> EvaluationCase:
    """Case 3: Correct tool selection for a task."""
    return EvaluationCase(
        id=uuid4(),
        name="Tool Selection",
        input={
            "task": "Search the web for weather",
            "available_tools": ["web_search", "calculator", "file_read"],
        },
        expected_outcome={
            "selected_tool": "web_search",
            "reason": "Search task requires web_search",
        },
        criteria=[
            {"key": "selected_tool", "type": "eq", "expected": "web_search"},
        ],
    )


def _case_tool_failure_recovery() -> EvaluationCase:
    """Case 4: Recovery from tool failure."""
    return EvaluationCase(
        id=uuid4(),
        name="Tool Failure Recovery",
        input={
            "task": "Get weather data",
            "tool": "web_search",
            "failure": "timeout",
            "fallback_tool": "cached_response",
        },
        expected_outcome={
            "recovered": True,
            "strategy": "fallback_tool",
            "used_fallback": True,
        },
        criteria=[
            {"key": "recovered", "type": "eq", "expected": True},
            {"key": "strategy", "type": "eq", "expected": "fallback_tool"},
        ],
    )


def _case_multi_agent_collaboration() -> EvaluationCase:
    """Case 5: Multi-agent collaboration task."""
    return EvaluationCase(
        id=uuid4(),
        name="Multi-Agent Collaboration",
        input={
            "task": "Research and write a report",
            "agents": ["researcher", "writer", "reviewer"],
            "strategy": "sequential",
        },
        expected_outcome={
            "completed": True,
            "agents_used": ["researcher", "writer", "reviewer"],
            "final_output": "Report content",
        },
        criteria=[
            {"key": "completed", "type": "eq", "expected": True},
            {"key": "agents_used", "type": "contains", "expected": "researcher"},
            {"key": "agents_used", "type": "contains", "expected": "writer"},
        ],
    )


def _case_verification_failure() -> EvaluationCase:
    """Case 6: Verification detects a failure."""
    return EvaluationCase(
        id=uuid4(),
        name="Verification Failure Detection",
        input={
            "task": "Verify agent output",
            "output": {"answer": 5, "confidence": 0.3},
            "expected": {"answer": 4, "confidence": 0.8},
        },
        expected_outcome={
            "verification_status": "fail",
            "score_below_threshold": True,
            "recovery_triggered": True,
        },
        criteria=[
            {"key": "verification_status", "type": "in", "expected": ["fail", "uncertain"]},
            {"key": "score_below_threshold", "type": "eq", "expected": True},
        ],
    )


def _case_retry() -> EvaluationCase:
    """Case 7: Retry after transient failure."""
    return EvaluationCase(
        id=uuid4(),
        name="Retry After Transient Failure",
        input={
            "task": "API call",
            "failure_type": "timeout",
            "max_retries": 3,
            "attempt": 1,
        },
        expected_outcome={
            "retried": True,
            "attempt": 2,
            "success": True,
        },
        criteria=[
            {"key": "retried", "type": "eq", "expected": True},
            {"key": "success", "type": "eq", "expected": True},
        ],
    )


def _case_partial_completion() -> EvaluationCase:
    """Case 8: Partial completion when full recovery isn't possible."""
    return EvaluationCase(
        id=uuid4(),
        name="Partial Completion",
        input={
            "task": "Multi-step workflow",
            "total_steps": 5,
            "completed_steps": 3,
            "failed_steps": 1,
            "skipped_steps": 1,
        },
        expected_outcome={
            "partial": True,
            "completion_rate": 0.6,
            "confidence": 0.6,
        },
        criteria=[
            {"key": "partial", "type": "eq", "expected": True},
            {"key": "completion_rate", "type": "gte", "expected": 0.5},
        ],
    )
