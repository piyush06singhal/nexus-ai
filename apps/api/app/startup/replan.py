"""Replanning — bounded responses to real operating signals.

:class:`ReplanningEngine` detects a trigger (KPI underperformance, execution or
verification failure, resource shortage, budget threshold, major risk,
blockage, validation failure, changed assumptions, milestone miss) and chooses
one of a bounded set of responses (:class:`ReplanResponse`). The response is a
*decision*; separately the operating cycle applies it. Replanning is governed by
the ``replan`` autonomy action (which can require a gate) and is capped per
cycle by ``MAX_REPLANNING_ATTEMPTS``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.startup import (
    StartupFeedback,
    StartupProject,
    StartupProjectStatus,
)
from app.startup.autonomy import AutonomyService
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.projects import ProjectManager
from app.startup.types import ReplanDecision, ReplanResponse


class ReplanningEngine:
    """Detect triggers and choose a bounded replanning response."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._projects = ProjectManager(db)
        self._events = StartupEventLogger(db)

    def evaluate(
        self,
        *,
        company_id: UUID,
        mission_id: UUID | None = None,
        state: Any | None = None,
        execution_outcome: dict[str, Any] | None = None,
        trigger: str | None = None,
        checked: int = 0,
    ) -> ReplanDecision:
        """Choose a response for the strongest detected trigger.

        ``state`` is an observed :class:`StateSnapshot`; ``execution_outcome``
        the result of a cycle's EXECUTE stage. Returns a non-executing decision.
        """
        if checked >= settings.startup_max_replanning_attempts:
            return ReplanDecision(
                trigger=trigger or "attempt_limit",
                response=ReplanResponse.ESCALATE,
                reason=(
                    f"Replanning attempt cap ({settings.startup_max_replanning_attempts}) reached"
                ),
                actions=[{"kind": "escalate", "detail": "Engage a human operator"}],
                requires_approval=True,
            )

        signals = self._signals(company_id, state, execution_outcome)
        chosen = trigger or self._strongest(signals)
        response, reason, actions, requires_approval = self._respond(company_id, chosen, signals)

        decision = ReplanDecision(
            trigger=chosen,
            response=response,
            reason=reason,
            actions=actions,
            requires_approval=requires_approval,
        )
        self._events.log(
            action=StartupEvents.REPLAN_TRIGGERED,
            company_id=company_id,
            target_type="mission",
            target_id=mission_id or UUID(int=0),
            details=decision.to_dict(),
            outcome="warning" if response != ReplanResponse.CONTINUE else "success",
        )
        self._record_feedback(company_id, mission_id, decision)
        return decision

    def apply(
        self,
        *,
        company_id: UUID,
        decision: ReplanDecision,
        approved_gate_id: UUID | None = None,
        actor: str = "cycle",
    ) -> dict[str, Any]:
        """Apply a bounded response under governance; returns what actually ran."""
        try:
            AutonomyService(self._db).enforce(
                "replan",
                company_id,
                actor=actor,
                approved_gate_id=approved_gate_id,
            )
        except Exception:
            raise  # caller routes to an approval gate when REQUIRE_APPROVAL

        applied: list[dict[str, Any]] = []
        for action in decision.actions:
            kind = action.get("kind")
            if kind == "reprioritize_project" and action.get("project_id"):
                self._projects.update(
                    company_id,
                    UUID(action["project_id"]),
                    priority=int(action.get("priority", 0)),
                )
                applied.append({"action": kind, "ok": True})
            elif kind == "pause_project" and action.get("project_id"):
                # StartupProjectStatus has no 'paused'; BLOCKED is the interruption state.
                self._projects.lifecycle(company_id, UUID(action["project_id"]), "blocked")
                applied.append({"action": kind, "ok": True})
            elif kind == "activate_project" and action.get("project_id"):
                self._projects.lifecycle(company_id, UUID(action["project_id"]), "active")
                applied.append({"action": kind, "ok": True})
            else:
                applied.append({"action": kind, "ok": False, "requires_human": True})
        self._db.commit()
        return {"decision": decision.to_dict(), "applied": applied}

    # ── Signal detection ──────────────────────────────────────────────

    def _signals(
        self,
        company_id: UUID,
        state: Any | None,
        execution_outcome: dict[str, Any] | None,
    ) -> dict[str, Any]:
        signals: dict[str, Any] = {}
        if state is not None:
            metrics = state.metrics if hasattr(state, "metrics") else {}
            dims = state.dimensions if hasattr(state, "dimensions") else {}
            signals["kpi"] = any(
                isinstance(k, dict) and (k.get("attainment") or 1.0) < 0.7
                for k in (metrics.get("kpis") or [])
            )
            signals["budget"] = (
                float((metrics.get("budget") or {}).get("utilization", 0.0) or 0.0) > 0.9
            )
            signals["risk"] = int(metrics.get("open_risks", 0) or 0) >= 3
            signals["verification"] = dims.get("verification", 1.0) < 0.7
        else:
            signals.update({"kpi": False, "budget": False, "risk": False, "verification": False})
        outcome = execution_outcome or {}
        signals["execution_failure"] = bool(outcome.get("failures"))
        signals["recovery"] = int(outcome.get("recovery_count", 0) or 0) >= 2
        return signals

    def _strongest(self, signals: dict[str, Any]) -> str:
        order = [
            ("execution_failure", "execution_failure"),
            ("kpi", "kpi_underperformance"),
            ("verification", "verification_failure"),
            ("budget", "budget_threshold"),
            ("risk", "major_risk"),
            ("recovery", "repeated_recovery"),
            ("blockage", "blockage"),
        ]
        for key, name in order:
            if signals.get(key):
                return name
        return "no_trigger"

    def _respond(
        self,
        company_id: UUID,
        trigger: str,
        signals: dict[str, Any],
    ) -> tuple[ReplanResponse, str, list[dict[str, Any]], bool]:
        if trigger == "kpi_underperformance":
            project = self._lowest_priority_active_project(company_id)
            if project is not None:
                return (
                    ReplanResponse.REPRIORITIZE,
                    "Underperforming KPIs: reprioritize the lowest-value active project",
                    [
                        {
                            "kind": "reprioritize_project",
                            "project_id": str(project.id),
                            "priority": 0,
                        }
                    ],
                    False,
                )
            return (
                ReplanResponse.REDUCE_SCOPE,
                "Underperforming KPIs with no low-priority project to reprioritize",
                [],
                True,
            )
        if trigger == "execution_failure":
            return (
                ReplanResponse.REASSIGN,
                "An execution failed; reassess task decomposition and assignment",
                [],
                False,
            )
        if trigger == "verification_failure":
            return (
                ReplanResponse.REPLAN,
                "Verification is failing; replan the affected work items",
                [],
                False,
            )
        if trigger == "budget_threshold":
            return (
                ReplanResponse.REQUEST_APPROVAL,
                "Budget utilization exceeded 90%; request approval for additional budget",
                [],
                True,
            )
        if trigger == "major_risk":
            return (
                ReplanResponse.PAUSE_PROJECT,
                "Three or more open risks; pause the riskiest work pending review",
                [],
                True,
            )
        if trigger == "repeated_recovery":
            return (
                ReplanResponse.REDUCE_SCOPE,
                "Repeated recoveries indicate over-scoped work; reduce scope",
                [],
                False,
            )
        if trigger == "blockage":
            return (
                ReplanResponse.REPLAN,
                "A dependency is blocked; replan around it",
                [{"kind": "replan_around_blockage"}],
                False,
            )
        return (
            ReplanResponse.CONTINUE,
            "No replanning trigger detected — continue the current plan",
            [],
            False,
        )

    def _lowest_priority_active_project(self, company_id: UUID) -> StartupProject | None:
        active = [
            p
            for p in self._projects.list_(company_id)
            if p.status in (StartupProjectStatus.ACTIVE, StartupProjectStatus.PLANNED)
        ]
        if not active:
            return None
        return min(active, key=lambda p: p.priority)

    def _record_feedback(
        self,
        company_id: UUID,
        mission_id: UUID | None,
        decision: ReplanDecision,
    ) -> None:
        feedback = StartupFeedback(
            company_id=company_id,
            mission_id=mission_id,
            source="replanning_engine",
            category=f"replan_{decision.trigger}",
            observation=f"Replanning response '{decision.response.value}': {decision.reason}",
            impact="Operating plan adjusted within bounded responses",
            confidence=0.7,
            recommendation=decision.reason,
        )
        self._db.add(feedback)
        self._db.commit()
