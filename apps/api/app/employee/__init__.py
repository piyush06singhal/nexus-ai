"""AI Employee OS — persistent organizational entities wrapping agents.

Phase 7 adds an identity/skill/goal/performance layer on top of the existing
Agent Runtime.  This package houses the domain logic; the DB models live in
``app.db.models.employee``.
"""

from app.employee.types import (
    AssignmentRequest,
    AssignmentResult,
    GoalStatus,
    SkillEntry,
    WorkloadSnapshot,
)

__all__ = [
    "AssignmentRequest",
    "AssignmentResult",
    "GoalStatus",
    "SkillEntry",
    "WorkloadSnapshot",
]
