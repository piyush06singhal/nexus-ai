"""Tests for AI Employee context builder (Phase 7)."""

import json

from app.employee.manager import EmployeeManager
from app.employee.types import SkillEntry


def test_build_context_includes_identity(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(
        name="context-worker",
        display_name="Context Worker",
        role="analyst",
        department="research",
        description="Does research",
    )
    ctx = mgr.build_context(emp.id)
    assert ctx["identity"]["name"] == "Context Worker"
    assert ctx["identity"]["role"] == "analyst"
    assert ctx["identity"]["department"] == "research"


def test_build_context_includes_skills(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="context-skills")
    mgr.add_skill(emp.id, SkillEntry(skill_id="s1", name="python", proficiency=0.9))

    ctx = mgr.build_context(emp.id)
    assert "skills" in ctx
    assert len(ctx["skills"]) == 1
    assert ctx["skills"][0]["name"] == "python"


def test_build_context_includes_goals(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="context-goals")
    mgr.create_goal(emp.id, title="Ship X")
    # Activate the goal so it appears in context
    goal = mgr.goals.get_goals(emp.id)[0]
    mgr.goals.update_progress(goal.id, progress=0.4)

    ctx = mgr.build_context(emp.id)
    assert "goals" in ctx
    assert ctx["goals"][0]["title"] == "Ship X"


def test_build_context_includes_policies(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(
        name="context-policies",
        policies={"max_concurrent_tasks": 5, "requires_verification": True},
    )
    ctx = mgr.build_context(emp.id)
    assert "policies" in ctx
    assert ctx["policies"]["requires_verification"] is True


def test_build_context_includes_tools(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="context-tools", tools=["web_search", "calculator"])

    ctx = mgr.build_context(emp.id)
    assert ctx["tools"] == ["web_search", "calculator"]


def test_build_context_includes_responsibilities(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="context-resp", responsibilities=["Analyze data", "Write reports"])

    ctx = mgr.build_context(emp.id)
    assert ctx["responsibilities"] == ["Analyze data", "Write reports"]


def test_build_context_truncates_to_budget(db):
    from app.employee.context import EmployeeContextBuilder

    mgr = EmployeeManager(db)
    emp = mgr.create(name="context-trunc", description="A" * 50000)

    # Use the context builder directly with a small token budget
    builder = EmployeeContextBuilder(db)
    ctx = builder.build_context(emp.id, max_tokens=10)
    total_chars = sum(len(json.dumps(v)) for v in ctx.values() if isinstance(v, (dict, list)))
    # Should be truncated — total should be less than full description
    assert total_chars < 50000


def test_build_context_with_task_description(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="context-task")

    ctx = mgr.build_context(emp.id, task_description="Analyze Q3 sales data")
    assert "current_task" in ctx
    assert ctx["current_task"]["description"] == "Analyze Q3 sales data"


def test_build_context_nonexistent_employee(db):
    mgr = EmployeeManager(db)
    from uuid import uuid4

    ctx = mgr.build_context(uuid4())
    assert ctx.get("error") == "employee_not_found"
