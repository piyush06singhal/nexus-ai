"""AI Employee OS — template service.

CRUD for reusable employee templates.  ``create_from_template`` clones the
template's config (role, skills, responsibilities, policies) but NOT private
memories, credentials, active tasks, or history.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.employee import (
    AIEmployee,
    EmployeeAvailability,
    EmployeeStatus,
    EmployeeTemplate,
)


class TemplateService:
    """Manages employee templates and template-based creation."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_templates(self) -> list[EmployeeTemplate]:
        """List all templates."""
        stmt = select(EmployeeTemplate).order_by(EmployeeTemplate.name)
        return list(self._db.execute(stmt).scalars().all())

    def get_template(self, template_id: UUID) -> EmployeeTemplate | None:
        """Fetch a template by ID."""
        return self._db.get(EmployeeTemplate, template_id)

    def create_template(
        self,
        *,
        name: str,
        description: str | None = None,
        role: str = "general",
        skills: list[dict[str, Any]] | None = None,
        responsibilities: list[str] | None = None,
        tools: list[str] | None = None,
        policies: dict[str, Any] | None = None,
        verification_policy: dict[str, Any] | None = None,
    ) -> EmployeeTemplate:
        """Create a new template."""
        template = EmployeeTemplate(
            name=name,
            description=description,
            role=role,
            skills=json.dumps(skills) if skills else None,
            responsibilities=json.dumps(responsibilities) if responsibilities else None,
            tools=json.dumps(tools) if tools else None,
            policies=json.dumps(policies) if policies else None,
            verification_policy=json.dumps(verification_policy) if verification_policy else None,
        )
        self._db.add(template)
        self._db.flush()
        return template

    def create_employee_from_template(
        self,
        template_id: UUID,
        *,
        name: str,
        display_name: str | None = None,
        agent_id: UUID | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> AIEmployee | None:
        """Create a new employee from a template, applying optional overrides.

        Clones: role, skills, responsibilities, tools, policies.
        Does NOT clone: memories, credentials, active tasks, history, goals.
        """
        template = self._db.get(EmployeeTemplate, template_id)
        if template is None:
            return None

        emp = AIEmployee(
            name=name,
            display_name=display_name or name,
            description=template.description,
            role=template.role,
            skills=template.skills,
            responsibilities=template.responsibilities,
            tools=template.tools,
            policies=template.policies,
            status=EmployeeStatus.DRAFT,
            availability=EmployeeAvailability.UNAVAILABLE,
            agent_id=agent_id,
            memory_namespace=f"employee:{name}",
        )

        # Apply overrides
        if overrides:
            if "role" in overrides:
                emp.role = overrides["role"]
            if "description" in overrides:
                emp.description = overrides["description"]
            if "skills" in overrides:
                emp.skills = json.dumps(overrides["skills"])
            if "responsibilities" in overrides:
                emp.responsibilities = json.dumps(overrides["responsibilities"])
            if "tools" in overrides:
                emp.tools = json.dumps(overrides["tools"])
            if "policies" in overrides:
                emp.policies = json.dumps(overrides["policies"])

        self._db.add(emp)
        self._db.flush()
        return emp
