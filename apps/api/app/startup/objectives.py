"""Objective decomposition — mission → strategic/operational objectives → goals.

:class:`ObjectiveDecomposer` breaks a mission's business/product objectives into
an explicit chain of company goals (each preserving parent, rationale, success
criteria, owner, priority, deadline, and resource link) so every goal is
traceable back to the mission. It also derives the per-project objectives a
startup plan's projects need. Pure structure: it decides *what* the goals are,
never *how* they are executed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.company.goals import GoalManager
from app.db.models.company import GoalScopeType
from app.db.models.startup import Mission, MissionGraphRelation, StartupPlan
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.graph import MissionGraphBuilder


class ObjectiveDecomposer:
    """Create a traceable objective → goal hierarchy for a mission."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._goals = GoalManager(db)
        self._events = StartupEventLogger(db)

    def decompose(self, mission: Mission) -> list[dict]:
        """Company goals derived from the mission's business/product objectives.

        Each company goal carries a ``rationale`` rooted in the mission and a
        direct ``derived_from`` mission-graph edge, so goals are never orphans.
        """
        plan = self._latest_plan(mission)
        objectives: list[tuple[str, str | None]] = []
        for field in ("business_objectives", "product_objectives"):
            for obj in self._plans_list(getattr(plan, field)) if plan else []:
                title, description = _objective_parts(obj)
                if title:
                    objectives.append((title, description))
        if not objectives and mission.analysis:
            analysis = _loads(mission.analysis)
            if isinstance(analysis, dict):
                objectives = [
                    (str(o), "Derived from mission analysis")
                    for o in (analysis.get("objectives") or [])
                    if str(o)
                ]

        created: list[dict] = []
        for i, (title, description) in enumerate(objectives[:8], start=1):
            goal = self._goals.create(
                company_id=mission.company_id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=mission.company_id,
                title=title,
                description=description or "Derived from the startup plan",
                priority=i,
                target=_goal_target(mission, i),
                metric="goal_progress",
            )
            MissionGraphBuilder(self._db).link(
                company_id=mission.company_id,
                source_type="goal",
                source_id=goal.id,
                target_type="mission",
                target_id=mission.id,
                relation=MissionGraphRelation.DERIVED_FROM,
                metadata={"rationale": "Company objective decomposed from mission"},
            )
            created.append(self._goals.to_dict(goal))
        self._events.log(
            action=StartupEvents.MISSION_PLANNED,
            company_id=mission.company_id,
            target_type="mission",
            target_id=mission.id,
            details={"goals": len(created)},
            outcome="success",
        )
        return created

    def project_objectives(self, mission: Mission, project: dict) -> dict:
        """Attach an objective + rationale to a startup project from its plan row."""
        return {
            "objective": project.get("objective") or project.get("description"),
            "rationale": f"Contributes to mission '{mission.title}'",
            "success_criteria": [str(s) for s in (project.get("success_criteria") or [])],
        }

    # ── Helpers ───────────────────────────────────────────────────────

    def _latest_plan(self, mission: Mission) -> StartupPlan | None:
        from sqlalchemy import select

        stmt = (
            select(StartupPlan)
            .where(StartupPlan.mission_id == mission.id)
            .order_by(StartupPlan.created_at.desc())
        )
        plan = self._db.scalar(stmt)
        return plan if plan is not None else None

    def _plans_list(self, raw: str | None) -> list:
        return _loads_list(raw)


def _loads(raw: str | None) -> dict:
    import json

    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _loads_list(raw: str | None) -> list:
    import json

    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _objective_parts(obj) -> tuple[str | None, str | None]:
    if isinstance(obj, str):
        return obj, None
    if isinstance(obj, dict):
        title = obj.get("title") or obj.get("objective")
        return str(title) if title else None, obj.get("description")
    return None, None


def _goal_target(mission: Mission, index: int) -> str | None:
    """Use the mission's first success criterion as the lead goal's target."""
    if index != 1:
        return None
    criteria = _loads_list(mission.success_criteria)
    return str(criteria[0]) if criteria else None
