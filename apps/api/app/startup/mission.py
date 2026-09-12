"""Mission management — lifecycle + analysis/validation/plan orchestration.

:class:`MissionManager` owns the mission lifecycle (create → analyze → validate
→ plan → activate → pause/cancel → complete) and drives the default (deterministic)
pipeline: analysis via :class:`DeterministicMissionAnalyzer`, validation via
:class:`MissionValidator`, strategy via :class:`DeterministicStrategicPlanner`,
a derived startup plan, and goal decomposition via :class:`ObjectiveDecomposer`.

Missions are company-scoped (a mission always belongs to a Phase 8 company) and
every state it passes through is recorded on the mission graph + event log so
the chain from intent to operating company is fully traceable.
"""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.startup import (
    Mission,
    MissionGraphRelation,
    MissionStatus,
    StartupPlan,
    StartupPlanStatus,
    StrategicPlan,
    StrategicPlanStatus,
)
from app.startup.analyze import run_analysis
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.graph import MissionGraphBuilder
from app.startup.objectives import ObjectiveDecomposer
from app.startup.strategy import DeterministicStrategicPlanner
from app.startup.types import MissionAnalysisResult, ValidationResult
from app.startup.validate import MissionValidator

_TRANSITIONS: dict[MissionStatus, set[MissionStatus]] = {
    MissionStatus.DRAFT: {MissionStatus.ANALYZING, MissionStatus.CANCELLED},
    MissionStatus.ANALYZING: {MissionStatus.PLANNED, MissionStatus.PAUSED, MissionStatus.CANCELLED},
    MissionStatus.PLANNED: {MissionStatus.ACTIVE, MissionStatus.PAUSED, MissionStatus.CANCELLED},
    MissionStatus.ACTIVE: {
        MissionStatus.PAUSED,
        MissionStatus.BLOCKED,
        MissionStatus.COMPLETED,
        MissionStatus.CANCELLED,
    },
    MissionStatus.PAUSED: {MissionStatus.ACTIVE, MissionStatus.CANCELLED},
    MissionStatus.BLOCKED: {MissionStatus.ACTIVE, MissionStatus.CANCELLED},
    MissionStatus.COMPLETED: {MissionStatus.ACTIVE},
    MissionStatus.FAILED: {MissionStatus.PLANNED, MissionStatus.CANCELLED},
    MissionStatus.CANCELLED: set(),
}


class MissionManager:
    """Create, list, update, and drive startup missions through their lifecycle."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    # ── CRUD ───────────────────────────────────────────────────────────

    def create(
        self,
        *,
        company_id: UUID,
        title: str,
        mission_statement: str,
        description: str | None = None,
        desired_outcome: str | None = None,
        target_market: str | None = None,
        constraints: list[str] | None = None,
        assumptions: list[str] | None = None,
        success_criteria: list[str] | None = None,
        strategic_context: dict[str, Any] | None = None,
        priority: int = 0,
        owner_id: UUID | None = None,
    ) -> Mission:
        mission = Mission(
            company_id=company_id,
            title=title,
            mission_statement=mission_statement,
            description=description,
            desired_outcome=desired_outcome,
            target_market=target_market,
            constraints=_dump_list(constraints),
            assumptions=_dump_list(assumptions),
            success_criteria=_dump_list(success_criteria),
            strategic_context=_dumps(strategic_context),
            priority=priority,
            owner_id=owner_id,
            status=MissionStatus.DRAFT,
        )
        self._db.add(mission)
        self._db.commit()
        self._events.log(
            action=StartupEvents.MISSION_CREATED,
            company_id=company_id,
            target_type="mission",
            target_id=mission.id,
            details={"title": title},
            outcome="success",
        )
        return mission

    def get(self, company_id: UUID, mission_id: UUID) -> Mission | None:
        mission = self._db.get(Mission, mission_id)
        if mission is None or mission.company_id != company_id:
            return None
        return mission

    def list_(self, company_id: UUID) -> list[Mission]:
        stmt = (
            select(Mission)
            .where(Mission.company_id == company_id)
            .order_by(Mission.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def update(self, company_id: UUID, mission_id: UUID, **fields: Any) -> Mission:
        mission = self._require(company_id, mission_id)
        _json_keys = ("constraints", "assumptions", "success_criteria", "strategic_context")
        _enum_only = ("status",)
        for key, value in fields.items():
            if value is None or not hasattr(mission, key):
                continue
            if key in _json_keys and isinstance(value, (list, dict)):
                setattr(mission, key, json.dumps(value))
            elif key in _enum_only:
                setattr(mission, key, MissionStatus(value))
            else:
                setattr(mission, key, value)
        self._db.commit()
        return mission

    # ── Lifecycle ──────────────────────────────────────────────────────

    def _transition(self, mission: Mission, target: MissionStatus) -> Mission:
        if target not in _TRANSITIONS.get(mission.status, set()):
            raise ValueError(f"Invalid mission transition: {mission.status.value} → {target.value}")
        mission.status = target
        if target == MissionStatus.ACTIVE and mission.started_at is None:
            from datetime import datetime

            mission.started_at = datetime.now(UTC)
        if target in (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED):
            from datetime import datetime

            mission.completed_at = datetime.now(UTC)
        self._db.commit()
        _event = {
            MissionStatus.ACTIVE: StartupEvents.MISSION_ACTIVATED,
            MissionStatus.PAUSED: StartupEvents.MISSION_PAUSED,
            MissionStatus.COMPLETED: StartupEvents.MISSION_COMPLETED,
            MissionStatus.CANCELLED: StartupEvents.MISSION_CANCELLED,
        }.get(target)
        if _event is not None:
            self._events.log(
                action=_event,
                company_id=mission.company_id,
                target_type="mission",
                target_id=mission.id,
                details={"status": target.value},
                outcome="success",
            )
        return mission

    def activate(self, company_id: UUID, mission_id: UUID) -> Mission:
        return self._transition(self._require(company_id, mission_id), MissionStatus.ACTIVE)

    def pause(self, company_id: UUID, mission_id: UUID) -> Mission:
        return self._transition(self._require(company_id, mission_id), MissionStatus.PAUSED)

    def complete(self, company_id: UUID, mission_id: UUID) -> Mission:
        return self._transition(self._require(company_id, mission_id), MissionStatus.COMPLETED)

    def cancel(self, company_id: UUID, mission_id: UUID) -> Mission:
        return self._transition(self._require(company_id, mission_id), MissionStatus.CANCELLED)

    # ── Pipeline ───────────────────────────────────────────────────────

    def analyze(self, mission: Mission) -> MissionAnalysisResult:
        """Run the default analysis and persist it (status → analyzing)."""
        mission = self._require(mission.company_id, mission.id)
        mission.status = MissionStatus.ANALYZING
        self._db.commit()
        result = run_analysis(self._db, mission)
        self._events.log(
            action=StartupEvents.MISSION_ANALYZED,
            company_id=mission.company_id,
            target_type="mission",
            target_id=mission.id,
            details={"objectives": len(result.objectives)},
            outcome="success",
        )
        return result

    def validate(self, mission: Mission) -> ValidationResult:
        """Run checklist validation; persist the verdict (`mission.validation`)."""
        mission = self._require(mission.company_id, mission.id)
        result = MissionValidator(self._db).validate(mission)
        mission.validation = json.dumps(result.to_dict(), default=str)
        self._db.commit()
        self._events.log(
            action=StartupEvents.MISSION_VALIDATED,
            company_id=mission.company_id,
            target_type="mission",
            target_id=mission.id,
            details={"ok": result.ok, "errors": len(result.issues)},
            outcome="success" if result.ok else "feedback",
        )
        return result

    def plan(self, mission: Mission) -> dict[str, Any]:
        """Produce a strategic plan + derived startup plan for the mission.

        Deterministic by default: the strategy derives from the (persisted or
        freshly run) analysis, and the startup plan is built from the same
        analysis. Both rows + their mission-graph edges + goal decomposition are
        created here; bootstrap consumes the approved startup plan later.
        """
        mission = self._require(mission.company_id, mission.id)
        analysis = self._analysis_or_run(mission)

        strategy_data = DeterministicStrategicPlanner(self._db).plan(mission, analysis)
        strategy = StrategicPlan(
            mission_id=mission.id,
            vision=strategy_data.vision,
            objectives=_dumps(strategy_data.objectives),
            priorities=_dumps(strategy_data.priorities),
            expected_outcomes=_dumps(strategy_data.expected_outcomes),
            assumptions=_dumps(strategy_data.assumptions),
            risks=_dumps(strategy_data.risks),
            milestones=_dumps(strategy_data.milestones),
            dependencies=_dumps(strategy_data.dependencies),
            capabilities=_dumps(strategy_data.capabilities),
            resource_estimates=_dumps(strategy_data.resource_estimates),
            success_metrics=_dumps(strategy_data.success_metrics),
            status=StrategicPlanStatus.ACTIVE,
        )
        self._db.add(strategy)
        self._db.flush()
        MissionGraphBuilder(self._db).link(
            company_id=mission.company_id,
            source_type="strategic_plan",
            source_id=strategy.id,
            target_type="mission",
            target_id=mission.id,
            relation=MissionGraphRelation.DERIVED_FROM,
        )

        startup_plan = self._derive_startup_plan(mission, analysis, strategy, strategy_data)
        self._db.add(startup_plan)
        self._db.flush()
        MissionGraphBuilder(self._db).link(
            company_id=mission.company_id,
            source_type="startup_plan",
            source_id=startup_plan.id,
            target_type="strategic_plan",
            target_id=strategy.id,
            relation=MissionGraphRelation.DERIVED_FROM,
        )

        mission.status = MissionStatus.PLANNED
        self._db.commit()

        # Goal decomposition (each goal links `derived_from` the mission).
        ObjectiveDecomposer(self._db).decompose(mission)

        self._events.log(
            action=StartupEvents.MISSION_PLANNED,
            company_id=mission.company_id,
            target_type="mission",
            target_id=mission.id,
            details={
                "strategic_plan_id": str(strategy.id),
                "startup_plan_id": str(startup_plan.id),
            },
            outcome="success",
        )
        return {
            "mission_id": str(mission.id),
            "status": mission.status.value,
            "strategic_plan_id": str(strategy.id),
            "startup_plan_id": str(startup_plan.id),
        }

    # ── Helpers ────────────────────────────────────────────────────────

    def _analysis_or_run(self, mission: Mission) -> MissionAnalysisResult:
        if mission.analysis:
            loaded = _loads(mission.analysis)
            if isinstance(loaded, dict):
                return MissionAnalysisResult(**loaded)
        return self.analyze(mission)

    def _derive_startup_plan(
        self,
        mission: Mission,
        analysis: MissionAnalysisResult,
        strategy: StrategicPlan,
        strategy_data,
    ) -> StartupPlan:
        solution = analysis.proposed_solution or "the product"
        departments = _departments_for(analysis.required_capabilities)
        roles = [r for dept in departments for r in (dept.get("roles") or [])]
        products = [
            {
                "name": solution,
                "description": f"{solution} for {analysis.target_market or 'the target market'}",
                "product_type": "software",
                "target_users": [analysis.target_market] if analysis.target_market else [],
                "value_proposition": (analysis.problem or "Solve the mission's core problem"),
                "strategic_priority": 1,
                "success_metrics": analysis.success_criteria,
                "launch_criteria": analysis.success_criteria,
            }
        ]
        projects = [
            {
                "name": str(obj)[:120] if len(str(obj)) > 120 else str(obj),
                "objective": str(obj),
                "product": solution,
                "priority": rank,
                "success_criteria": analysis.success_criteria if rank == 1 else [],
            }
            for rank, obj in enumerate(analysis.objectives[:5], start=1)
        ]
        return StartupPlan(
            mission_id=mission.id,
            strategic_plan_id=strategy.id,
            business_objectives=_dumps(analysis.objectives),
            product_objectives=_dumps(
                [
                    {"title": s, "description": "Product launch success"}
                    for s in analysis.success_criteria
                ]
            ),
            market_objectives=_dumps(
                [f"Reach and understand {analysis.target_market}"] if analysis.target_market else []
            ),
            organization_objectives=_dumps(
                [f"Stand up {len(departments)} departments with a governed workforce"]
            ),
            operational_objectives=_dumps(
                ["Run bounded-autonomy operating cycles with feedback and replanning"]
            ),
            milestones=_dumps(analysis.unknowns[:8]),
            departments=_dumps(departments),
            roles=json.dumps(roles, default=str),
            capabilities=_dumps(analysis.required_capabilities),
            initial_products=json.dumps(products, default=str),
            initial_projects=json.dumps(projects, default=str),
            kpi_targets=json.dumps(
                {
                    "task_success_rate": 0.9,
                    "verification_rate": 0.9,
                    "budget_utilization": 0.8,
                },
                default=str,
            ),
            budget_allocation="{}",
            execution_priorities=_dumps(strategy_data.priorities),
            approval_requirements=json.dumps(
                [
                    {"action": "provision_employee", "gate": "company_bootstrap_approval"},
                    {"action": "launch_product", "gate": "product_launch_approval"},
                    {"action": "replan", "gate": "high_risk_action_approval"},
                    {"action": "allocate_budget", "gate": "budget_approval"},
                ],
                default=str,
            ),
            status=StartupPlanStatus.DRAFT,
        )

    def to_dict(self, mission: Mission) -> dict[str, Any]:
        return {
            "id": str(mission.id),
            "company_id": str(mission.company_id),
            "title": mission.title,
            "description": mission.description,
            "mission_statement": mission.mission_statement,
            "desired_outcome": mission.desired_outcome,
            "target_market": mission.target_market,
            "constraints": _loads_list(mission.constraints),
            "assumptions": _loads_list(mission.assumptions),
            "success_criteria": _loads_list(mission.success_criteria),
            "strategic_context": _loads(mission.strategic_context),
            "priority": mission.priority,
            "status": mission.status.value,
            "analysis": _loads(mission.analysis),
            "validation": _loads(mission.validation),
            "owner_id": str(mission.owner_id) if mission.owner_id else None,
            "started_at": mission.started_at.isoformat() if mission.started_at else None,
            "completed_at": mission.completed_at.isoformat() if mission.completed_at else None,
            "created_at": mission.created_at.isoformat() if mission.created_at else None,
            "updated_at": mission.updated_at.isoformat() if mission.updated_at else None,
        }

    def _require(self, company_id: UUID, mission_id: UUID) -> Mission:
        mission = self.get(company_id, mission_id)
        if mission is None:
            raise ValueError("Mission not found")
        return mission


# ── Module helpers ───────────────────────────────────────────────────────


def _departments_for(capabilities: list[str]) -> list[dict[str, Any]]:
    """Map required capabilities to a sensible startup-plan department set."""
    low = " ".join(capabilities).lower()
    departments: list[dict[str, Any]] = []
    if any(token in low for token in ("engineering", "product", "platform", "sdk", "ai", "ml")):
        departments.append(
            {
                "name": "Engineering",
                "mission": "Build and maintain the core product",
                "roles": [
                    {
                        "name": "engineering_specialist",
                        "title": "Engineering Specialist",
                        "authority_level": "individual_contributor",
                        "responsibilities": ["Build product capabilities"],
                        "required_skills": ["engineering"],
                    }
                ],
                "reports_to": "Executive",
            }
        )
    if "research" in low or "validation" in low:
        departments.append(
            {
                "name": "Research",
                "mission": "Validate problem/solution fit with evidence",
                "roles": [
                    {
                        "name": "research_specialist",
                        "title": "Research Specialist",
                        "authority_level": "individual_contributor",
                        "responsibilities": ["Validate the core problem"],
                        "required_skills": ["research"],
                    }
                ],
                "reports_to": "Engineering",
            }
        )
    if "marketing" in low or "go-to-market" in low:
        departments.append(
            {
                "name": "Marketing",
                "mission": "Reach and acquire the target market",
                "roles": [
                    {
                        "name": "marketing_specialist",
                        "title": "Marketing Specialist",
                        "authority_level": "individual_contributor",
                        "responsibilities": ["Reach the target market"],
                        "required_skills": ["marketing"],
                    }
                ],
                "reports_to": "Executive",
            }
        )
    departments.append(
        {
            "name": "Operations",
            "mission": "Run and govern the startup's cycle operations",
            "roles": [
                {
                    "name": "operations_specialist",
                    "title": "Operations Specialist",
                    "authority_level": "individual_contributor",
                    "responsibilities": ["Execute operating objectives"],
                    "required_skills": ["operations"],
                }
            ],
        }
    )
    departments.append(
        {
            "name": "Executive",
            "mission": "Own the mission, strategy, and bounded-autonomy governance",
            "roles": [
                {
                    "name": "founder_ceo",
                    "title": "Founder & CEO",
                    "authority_level": "company_admin",
                    "responsibilities": [
                        "Own mission and strategy",
                        "Approve high-risk autonomous actions",
                    ],
                    "required_skills": ["leadership", "strategy"],
                }
            ],
            "reports_to": None,
        }
    )
    return departments


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _dump_list(value: list[str] | None) -> str | None:
    if not value:
        return None
    return json.dumps([str(v) for v in value])


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _loads_list(raw: str | None) -> list[Any]:
    value = _loads(raw)
    return list(value) if isinstance(value, list) else []
