"""AI Company Layer — organizational role definitions.

Roles are reusable organizational definitions (title, responsibilities,
required skills, authority level/scope, default policies, KPIs, compatible
departments). Roles remain separate from the underlying Agent. A company may
also use global roles (``company_id is None``).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.company import (
    AuthorityLevel,
    OrganizationalRole,
)


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return None


class RoleManager:
    """Create, list, and query organizational roles."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        name: str,
        title: str,
        company_id: UUID | None = None,
        description: str | None = None,
        responsibilities: list[str] | None = None,
        required_skills: list[str] | None = None,
        authority_level: AuthorityLevel = AuthorityLevel.INDIVIDUAL_CONTRIBUTOR,
        authority_scope: dict[str, Any] | None = None,
        default_policies: dict[str, Any] | None = None,
        kpis: list[str] | None = None,
        compatible_departments: list[str] | None = None,
    ) -> OrganizationalRole:
        """Create a role, scoped to a company (or global when ``company_id`` is None)."""
        role = OrganizationalRole(
            company_id=company_id,
            name=name,
            title=title or name,
            description=description,
            responsibilities=_dumps(responsibilities),
            required_skills=_dumps(required_skills),
            authority_level=authority_level,
            authority_scope=_dumps(authority_scope),
            default_policies=_dumps(default_policies),
            kpis=_dumps(kpis),
            compatible_departments=_dumps(compatible_departments),
        )
        self._db.add(role)
        self._db.commit()
        return role

    def get(self, role_id: UUID) -> OrganizationalRole | None:
        return self._db.get(OrganizationalRole, role_id)

    def list_(
        self,
        *,
        company_id: UUID | None = None,
        authority_level: AuthorityLevel | None = None,
        limit: int = 100,
    ) -> list[OrganizationalRole]:
        """List roles. When ``company_id`` is given, includes global + company-scoped."""
        stmt = select(OrganizationalRole).order_by(OrganizationalRole.title)
        if company_id is not None:
            stmt = stmt.where(
                (OrganizationalRole.company_id == company_id)
                | (OrganizationalRole.company_id.is_(None))
            )
        if authority_level is not None:
            stmt = stmt.where(OrganizationalRole.authority_level == authority_level)
        stmt = stmt.limit(limit)
        return list(self._db.execute(stmt).scalars().all())

    def find_by_name(self, company_id: UUID, name: str) -> OrganizationalRole | None:
        """Find a company-scoped role by name (falling back to global roles)."""
        stmt = select(OrganizationalRole).where(
            OrganizationalRole.name == name,
            (OrganizationalRole.company_id == company_id)
            | (OrganizationalRole.company_id.is_(None)),
        )
        return self._db.scalar(stmt)

    def to_dict(self, role: OrganizationalRole) -> dict[str, Any]:
        """Serialize a role for API output."""
        return {
            "id": str(role.id),
            "company_id": str(role.company_id) if role.company_id else None,
            "name": role.name,
            "title": role.title,
            "description": role.description,
            "responsibilities": _loads(role.responsibilities),
            "required_skills": _loads(role.required_skills),
            "authority_level": role.authority_level.value,
            "authority_scope": _loads(role.authority_scope),
            "default_policies": _loads(role.default_policies),
            "kpis": _loads(role.kpis),
            "compatible_departments": _loads(role.compatible_departments),
            "created_at": role.created_at.isoformat() if role.created_at else None,
            "updated_at": role.updated_at.isoformat() if role.updated_at else None,
        }
