"""AI Employee OS — skill assessment and management.

Evaluates employee skills using execution data.  Does not arbitrarily change
scores — every update is backed by evidence.  Configurable evaluation policies.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.employee import AIEmployee
from app.employee.types import SkillEntry


class SkillAssessor:
    """Evaluates and manages employee skills."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_skills(self, employee_id: UUID) -> list[SkillEntry]:
        """Load skills from the employee record."""
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return []
        if not emp.skills:
            return []
        raw = json.loads(emp.skills)
        return [SkillEntry(**s) for s in raw]

    def update_skills(self, employee_id: UUID, skills: list[SkillEntry]) -> None:
        """Persist a full skill list for the employee."""
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return
        emp.skills = json.dumps([_skill_to_dict(s) for s in skills])

    def record_skill_use(
        self,
        employee_id: UUID,
        skill_id: str,
        *,
        success: bool = True,
        quality: float = 0.5,
    ) -> SkillEntry | None:
        """Record an instance of skill usage, adjusting proficiency.

        Proficiency increases on success (capped at 1.0) and decreases on
        failure (floored at 0.0).  The adjustment magnitude is proportional
        to the current proficiency (beginners learn faster).
        """
        skills = self.get_skills(employee_id)
        target: SkillEntry | None = None
        for s in skills:
            if s.skill_id == skill_id:
                target = s
                break

        if target is None:
            return None

        target.evidence_count += 1
        target.last_used = datetime.now(UTC)

        # Adaptive learning rate: beginners improve faster.
        base_rate = 0.05 * (1.0 - target.proficiency * 0.5)
        if success:
            delta = base_rate * quality
            target.proficiency = min(1.0, target.proficiency + delta)
            target.confidence = min(1.0, target.confidence + 0.02)
        else:
            delta = base_rate * 0.5
            target.proficiency = max(0.0, target.proficiency - delta)
            target.confidence = max(0.0, target.confidence - 0.03)

        self.update_skills(employee_id, skills)
        return target

    def add_skill(self, employee_id: UUID, skill: SkillEntry) -> None:
        """Add a new skill (or update if skill_id already exists)."""
        skills = self.get_skills(employee_id)
        for i, existing in enumerate(skills):
            if existing.skill_id == skill.skill_id:
                skills[i] = skill
                self.update_skills(employee_id, skills)
                return
        skills.append(skill)
        self.update_skills(employee_id, skills)

    def remove_skill(self, employee_id: UUID, skill_id: str) -> bool:
        """Remove a skill by ID.  Returns True if found and removed."""
        skills = self.get_skills(employee_id)
        original_len = len(skills)
        skills = [s for s in skills if s.skill_id != skill_id]
        if len(skills) < original_len:
            self.update_skills(employee_id, skills)
            return True
        return False

    def match_skills(self, employee_id: UUID, required: list[str]) -> tuple[float, list[str]]:
        """Score how well an employee's skills match a set of required skill names.

        Returns (score 0.0–1.0, list of matched skill names).
        """
        skills = self.get_skills(employee_id)
        skill_names = {s.name.lower(): s for s in skills}
        matched: list[str] = []
        for req in required:
            if req.lower() in skill_names:
                matched.append(req)
        if not required:
            return 1.0, []
        return len(matched) / len(required), matched


def _skill_to_dict(s: SkillEntry) -> dict[str, Any]:
    """Serialize a ``SkillEntry`` to a JSON-compatible dict."""
    d: dict[str, Any] = {
        "skill_id": s.skill_id,
        "name": s.name,
        "category": s.category,
        "proficiency": s.proficiency,
        "confidence": s.confidence,
        "evidence_count": s.evidence_count,
        "tags": s.tags,
    }
    if s.last_used is not None:
        d["last_used"] = s.last_used.isoformat()
    return d
