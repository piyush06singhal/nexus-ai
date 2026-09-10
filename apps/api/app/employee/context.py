"""AI Employee OS — context builder.

Builds employee-specific context for execution: identity, role, responsibilities,
goals, relevant memories, current tasks, available tools, and policies.

Applies relevance filtering and context budgets — never sends all info to
every execution.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.employee import AIEmployee
from app.employee.goals import GoalTracker
from app.employee.skills import SkillAssessor


class EmployeeContextBuilder:
    """Builds employee-specific context for task execution."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._skills = SkillAssessor(db)
        self._goals = GoalTracker(db)

    def build_context(
        self,
        employee_id: UUID,
        *,
        task_description: str = "",
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Build a context dict for the employee's next execution.

        Sections are assembled in priority order and truncated to the
        ``max_tokens`` budget (approximated as characters / 4).
        """
        if max_tokens is None:
            max_tokens = settings.employee_context_max_tokens
        budget_chars = max_tokens * 4

        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return {"error": "employee_not_found", "employee_id": str(employee_id)}

        sections: list[tuple[str, Any]] = []

        # 1. Identity & role (always included, highest priority)
        identity = {
            "name": emp.display_name or emp.name,
            "role": emp.role,
            "department": emp.department,
            "description": emp.description,
        }
        sections.append(("identity", identity))

        # 2. Responsibilities
        if emp.responsibilities:
            responsibilities = json.loads(emp.responsibilities)
            sections.append(("responsibilities", responsibilities))

        # 3. Active goals (top 5 by priority)
        from app.employee.types import GoalStatus as GS

        goals = self._goals.get_goals(employee_id, status=GS.ACTIVE)
        goal_data = []
        for g in goals[:5]:
            goal_data.append(
                {
                    "title": g.title,
                    "description": g.description,
                    "progress": g.progress,
                    "target": g.target,
                    "metric": g.metric,
                }
            )
        if goal_data:
            sections.append(("goals", goal_data))

        # 4. Relevant skills (top 5 by proficiency)
        skills = self._skills.get_skills(employee_id)
        top_skills = sorted(skills, key=lambda s: s.proficiency, reverse=True)[:5]
        if top_skills:
            skill_data = [
                {"name": s.name, "proficiency": s.proficiency, "category": s.category}
                for s in top_skills
            ]
            sections.append(("skills", skill_data))

        # 5. Available tools
        if emp.tools:
            tools = json.loads(emp.tools)
            sections.append(("tools", tools))

        # 6. Policies (truncated)
        if emp.policies:
            policies = json.loads(emp.policies)
            sections.append(("policies", policies))

        # 7. Task-specific context
        if task_description:
            sections.append(("current_task", {"description": task_description}))

        # Truncate to budget (approximate)
        result: dict[str, Any] = {"employee_id": str(employee_id)}
        used_chars = 0
        for key, value in sections:
            serialized = json.dumps(value)
            if used_chars + len(serialized) > budget_chars:
                # Truncate this section to fit
                remaining = budget_chars - used_chars
                if remaining > 100:
                    result[key] = json.loads(serialized[:remaining])
                break
            result[key] = value
            used_chars += len(serialized)

        return result
