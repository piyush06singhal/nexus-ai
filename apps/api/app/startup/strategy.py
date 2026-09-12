"""Strategic planning — translate a mission analysis into a strategy.

Produces a :class:`StrategyPlanData` (vision, objectives, priorities, expected
outcomes, assumptions, risks, milestones, dependencies, capabilities, resource
estimates, success metrics). A planner only produces a plan — it never
executes. Default implementation is deterministic; the model variant delegates
to ``ModelProvider.structured_output``.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.ai.interfaces import ModelProvider
from app.db.models.startup import Mission
from app.startup.types import MissionAnalysisResult, StrategyPlanData


class StrategicPlanner(Protocol):
    """Produce a strategic plan from a mission analysis."""

    def plan(self, mission: Mission, analysis: MissionAnalysisResult) -> StrategyPlanData: ...


class DeterministicStrategicPlanner:
    """Rule-based strategic planning from a structured mission analysis."""

    def __init__(self, db: Session | None = None) -> None:
        self._db = db

    def plan(self, mission: Mission, analysis: MissionAnalysisResult) -> StrategyPlanData:
        objectives = self._build_objectives(mission, analysis)
        priorities = self._build_priorities(analysis)
        milestones = self._build_milestones(analysis)
        capabilities = analysis.required_capabilities or [
            "product engineering",
            "operations",
        ]
        success_metrics = analysis.success_criteria or []
        return StrategyPlanData(
            vision=self._build_vision(mission, analysis),
            objectives=objectives,
            priorities=priorities,
            expected_outcomes=[f"Impact on {m}" for m in success_metrics]
            or ["Mission objectives are met on the articulated timeline"],
            assumptions=analysis.assumptions,
            risks=analysis.risks,
            milestones=milestones,
            dependencies=[f"Capability: {c}" for c in capabilities],
            capabilities=capabilities,
            resource_estimates=self._resource_estimates(analysis),
            success_metrics=success_metrics or ["Mission milestones achieved"],
        )

    # ── Rule helpers ───────────────────────────────────────────────────

    def _build_vision(self, mission: Mission, analysis: MissionAnalysisResult) -> str:
        solution = analysis.proposed_solution or "the product"
        market = analysis.target_market or "the target market"
        return f"To be the trusted {solution} for {market}"

    def _build_objectives(self, mission: Mission, analysis: MissionAnalysisResult) -> list[dict]:
        objectives: list[dict] = []
        for rank, objective in enumerate(analysis.objectives, start=1):
            objectives.append(
                {
                    "id": f"obj-{rank}",
                    "title": objective,
                    "rationale": "Derived from mission analysis",
                    "owner": None,
                    "priority": rank,
                    "deadline": None,
                    "success_criteria": analysis.success_criteria[:]
                    if rank == 1
                    else [f"{objective} achieved"],
                }
            )
        return objectives

    def _build_priorities(self, analysis: MissionAnalysisResult) -> list[str]:
        priorities: list[str] = []
        if analysis.proposed_solution:
            priorities.append("Build and validate the core solution")
        if analysis.target_market:
            priorities.append("Reach and understand the target market")
        if analysis.success_criteria:
            priorities.append("Prove all success criteria with evidence")
        priorities.append("Establish operating rhythm (cycles, feedback, replanning)")
        return priorities

    def _build_milestones(self, analysis: MissionAnalysisResult) -> list[dict]:
        timeline = analysis.timeline or "2 quarters"
        milestones = [
            {
                "title": "Validated mission & strategy",
                "description": "Analysis, validation, and startup plan approved",
                "target": timeline,
            },
            {
                "title": "Company bootstrapped",
                "description": "Departments, roles, workforce, and budget operational",
                "target": timeline,
            },
            {
                "title": "First product shipped",
                "description": (
                    f"{analysis.proposed_solution or 'The product'} available to early users"
                ),
                "target": timeline,
            },
            {
                "title": "Success criteria measured",
                "description": "KPIs tracked across operating cycles",
                "target": timeline,
            },
        ]
        return milestones

    def _resource_estimates(self, analysis: MissionAnalysisResult) -> dict:
        count = max(3, len(analysis.required_capabilities or []))
        return {
            "employees": {"estimate": count, "unit": "employees"},
            "budget": {"estimate": None, "unit": "USD/month"},
            "cycles": {"estimate": 4, "unit": "operating cycles"},
        }


class ModelStrategicPlanner:
    """Provider-agnostic model-backed strategic planning."""

    def __init__(self, db: Session | None, provider: ModelProvider) -> None:
        self._db = db
        self._provider = provider

    def plan(self, mission: Mission, analysis: MissionAnalysisResult) -> StrategyPlanData:
        from pydantic import BaseModel, Field

        class StrategySchema(BaseModel):
            vision: str | None = None
            objectives: list[dict] = Field(default_factory=list)
            priorities: list[str] = Field(default_factory=list)
            expected_outcomes: list[str] = Field(default_factory=list)
            assumptions: list[str] = Field(default_factory=list)
            risks: list[str] = Field(default_factory=list)
            milestones: list[dict] = Field(default_factory=list)
            dependencies: list[str] = Field(default_factory=list)
            capabilities: list[str] = Field(default_factory=list)
            resource_estimates: dict = Field(default_factory=dict)
            success_metrics: list[str] = Field(default_factory=list)

        result = self._provider.structured_output(
            [
                {
                    "role": "user",
                    "content": (
                        "Produce a strategic plan from this mission analysis.\n"
                        f"Mission: {mission.mission_statement}\n"
                        f"Analysis: {analysis.to_dict()}"
                    ),
                }
            ],
            schema=StrategySchema,
        )
        return StrategyPlanData(
            vision=result.vision,
            objectives=list(result.objectives),
            priorities=list(result.priorities),
            expected_outcomes=list(result.expected_outcomes),
            assumptions=list(result.assumptions),
            risks=list(result.risks),
            milestones=list(result.milestones),
            dependencies=list(result.dependencies),
            capabilities=list(result.capabilities),
            resource_estimates=dict(result.resource_estimates),
            success_metrics=list(result.success_metrics),
        )
