"""Tests for deterministic planning / task decomposition (spec §5, §6, §33)."""

from __future__ import annotations

import pytest

from app.orchestration.planner import DeterministicPlanner, validate_plan
from app.orchestration.types import ExecutionPlan, PlannerError, PlanTask


def test_market_objective_decomposes_into_four_tasks():
    plan = DeterministicPlanner().create_plan(
        "Analyze the competitive market and write a report", [], {}
    )
    assert plan.strategy == "deterministic"
    names = [t.name for t in plan.tasks]
    assert "research" in names
    assert "analysis" in names
    assert "fact_checking" in names
    assert "writing" in names


def test_writer_depends_on_all_prerequisite_tasks():
    plan = DeterministicPlanner().create_plan("Build a competitive market analysis report", [], {})
    writer = next(t for t in plan.tasks if t.name == "writing")
    assert set(writer.dependencies) == {"research", "analysis", "fact_checking"}


def test_generic_objective_falls_back_to_single_task():
    plan = DeterministicPlanner().create_plan("Hello world", [], {})
    assert len(plan.tasks) == 1
    assert plan.tasks[0].name == "complete"
    assert plan.tasks[0].required_capabilities == ["general"]


def test_valid_plan_passes_validation():
    plan = ExecutionPlan(
        objective="test",
        tasks=[
            PlanTask(name="a", required_capabilities=["general"], dependencies=[]),
            PlanTask(name="b", required_capabilities=["general"], dependencies=["a"]),
        ],
    )
    validate_plan(plan)  # should not raise


def test_empty_plan_rejected():
    with pytest.raises(PlannerError):
        validate_plan(ExecutionPlan(objective="x", tasks=[]))


def test_plan_without_objective_rejected():
    with pytest.raises(PlannerError):
        validate_plan(ExecutionPlan(objective="  ", tasks=[PlanTask(name="a")]))


def test_duplicate_task_names_rejected():
    with pytest.raises(PlannerError):
        validate_plan(
            ExecutionPlan(
                objective="x",
                tasks=[PlanTask(name="a"), PlanTask(name="a")],
            )
        )


def test_self_dependency_rejected():
    with pytest.raises(PlannerError):
        validate_plan(
            ExecutionPlan(
                objective="x",
                tasks=[PlanTask(name="a", dependencies=["a"])],
            )
        )


def test_unknown_dependency_rejected():
    with pytest.raises(PlannerError):
        validate_plan(
            ExecutionPlan(
                objective="x",
                tasks=[PlanTask(name="a", dependencies=["ghost"])],
            )
        )


def test_circular_dependency_rejected():
    with pytest.raises(PlannerError):
        validate_plan(
            ExecutionPlan(
                objective="x",
                tasks=[
                    PlanTask(name="a", dependencies=["b"]),
                    PlanTask(name="b", dependencies=["a"]),
                ],
            )
        )


def test_plan_tasks_have_capabilities():
    plan = DeterministicPlanner().create_plan("Write a competitive market research report", [], {})
    research = next(t for t in plan.tasks if t.name == "research")
    assert "research" in research.required_capabilities
    writing = next(t for t in plan.tasks if t.name == "writing")
    assert "writing" in writing.required_capabilities
