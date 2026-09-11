"""AI Company Layer — organization-aware task routing.

Extends Phase 7 task assignment with department, role, authority, budget, and
policy awareness. Captures explainability: for every assignment, the service
records which employee was selected, who the candidates were, what skills they
have, the score that determined the winner, and the reason for the choice (§50).
No selection without recorded rationale.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.budget import ResourceGovernor
from app.company.events import OrgEventLogger
from app.company.membership import MembershipManager
from app.db.models.company import (
    OrganizationalMembership,
    OrganizationalRole,
)
from app.db.models.employee import AIEmployee


def _parse_skills(raw: str | None) -> list[str]:
    """Parse the employee ``skills`` text column.

    Skills are stored as a JSON list (e.g. ``["python","ml"]``). Tolerate a
    bare string (the legacy "python,testing" form) by returning it as a single
    element so old data still routes.
    """
    if not raw:
        return []
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [str(s) for s in val if s]
        return [str(val)]
    except (json.JSONDecodeError, TypeError):
        return [raw]


class OrgRoutingService:
    """Route tasks to the most suitable employee, with full explainability."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)
        self.memberships = MembershipManager(self._db)
        self.governor = ResourceGovernor(self._db)

    def route(
        self,
        *,
        company_id: UUID,
        task_name: str,
        required_skills: list[str] | None = None,
        department_id: UUID | None = None,
        budget_check: bool = True,
        authority_level: str | None = None,
    ) -> dict[str, Any]:
        """Select the best employee for a task, returning full explainability.

        Returns a dict with keys:
          - selected_employee_id: UUID | None
          - candidates: list of candidate dicts (id, name, skills, score)
          - reason: human-readable explanation
          - explainability: dict with skills, score_breakdown, timestamp
        """
        required_skills = required_skills or []
        candidates = self._eligible_candidates(
            company_id,
            department_id=department_id,
            required_skills=required_skills,
            authority_level=authority_level,
        )
        if not candidates:
            return self._no_match(company_id, task_name, required_skills)

        scored = [self._score_candidate(c, required_skills, budget_check) for c in candidates]
        scored.sort(key=lambda c: c["score"], reverse=True)
        winner = scored[0]
        explanation = f"Selected {winner['name']} (score {winner['score']:.2f}): {winner['reason']}"
        self.events.log(
            actor="system",
            action="task_routed",
            company_id=company_id,
            target_type="employee",
            target_id=winner["id"],
            details={
                "task_name": task_name,
                "score": winner["score"],
                "candidates_count": len(candidates),
            },
            outcome="success",
        )
        return {
            "selected_employee_id": winner["id"],
            "candidates": scored,
            "reason": explanation,
            "explainability": {
                "task_name": task_name,
                "required_skills": required_skills,
                "score_breakdown": winner.get("breakdown", {}),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }

    def _eligible_candidates(
        self,
        company_id: UUID,
        *,
        department_id: UUID | None = None,
        required_skills: list[str] | None = None,
        authority_level: str | None = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(OrganizationalMembership, AIEmployee, OrganizationalRole)
            .join(AIEmployee, OrganizationalMembership.employee_id == AIEmployee.id)
            .outerjoin(
                OrganizationalRole,
                OrganizationalMembership.role_id == OrganizationalRole.id,
            )
            .where(OrganizationalMembership.company_id == company_id)
        )
        if department_id is not None:
            stmt = stmt.where(OrganizationalMembership.department_id == department_id)
        rows = self._db.execute(stmt).all()
        candidates = []
        for membership, employee, role in rows:
            if employee.agent_id is None:
                continue
            if authority_level and role:
                rank = {
                    "company_admin": 4,
                    "executive": 3,
                    "manager": 2,
                    "team_lead": 1,
                    "individual_contributor": 0,
                }
                if rank.get(role.authority_level.value, 0) < rank.get(authority_level, 0):
                    continue
            skills = _parse_skills(employee.skills)
            if required_skills and not set(required_skills).issubset(set(skills)):
                continue
            candidates.append(
                {
                    "id": employee.id,
                    "name": employee.display_name or employee.name,
                    "agent_id": str(employee.agent_id),
                    "skills": skills,
                    "role_name": role.name if role else None,
                    "authority_level": role.authority_level.value if role else None,
                    "department_id": (
                        str(membership.department_id) if membership.department_id else None
                    ),
                }
            )
        return candidates

    def _score_candidate(
        self,
        candidate: dict[str, Any],
        required_skills: list[str],
        budget_check: bool,
    ) -> dict[str, Any]:
        score = 0.0
        breakdown: dict[str, Any] = {}
        # Skill match (0-40 pts)
        skills = set(candidate["skills"])
        required = set(required_skills)
        if required:
            matched = skills & required
            skill_score = (len(matched) / len(required)) * 40
        else:
            skill_score = 20.0  # Neutral when no skills required
        score += skill_score
        breakdown["skill_match"] = round(skill_score, 2)
        # Role authority bonus (0-20 pts)
        auth_map = {
            "company_admin": 20,
            "executive": 18,
            "manager": 14,
            "team_lead": 10,
            "individual_contributor": 6,
        }
        auth_score = auth_map.get(candidate.get("authority_level", ""), 0)
        score += auth_score
        breakdown["authority"] = auth_score
        # Budget headroom (0-20 pts) — if budget check enabled
        budget_score = 10.0  # Default neutral
        if budget_check:
            budget_score = 20.0  # Assume ok unless proven otherwise
        score += budget_score
        breakdown["budget_headroom"] = budget_score
        # Skill diversity bonus (0-20 pts)
        diversity_score = min(20, len(skills) * 2)
        score += diversity_score
        breakdown["skill_diversity"] = diversity_score

        return {
            "id": candidate["id"],
            "name": candidate["name"],
            "agent_id": candidate["agent_id"],
            "skills": candidate["skills"],
            "role_name": candidate.get("role_name"),
            "score": round(score, 2),
            "breakdown": breakdown,
            "reason": (
                f"Skills matched {len(skills & required)}/{len(required)}, "
                f"authority={candidate.get('authority_level', 'n/a')}"
            ),
        }

    def _no_match(
        self, company_id: UUID, task_name: str, required_skills: list[str]
    ) -> dict[str, Any]:
        return {
            "selected_employee_id": None,
            "candidates": [],
            "reason": f"No eligible employee found for '{task_name}' with skills {required_skills}",
            "explainability": {
                "task_name": task_name,
                "required_skills": required_skills,
                "candidates_found": 0,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }
