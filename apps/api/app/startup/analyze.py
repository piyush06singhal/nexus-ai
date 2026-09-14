"""Mission analysis — define what the mission actually means.

Produces a structured :class:`MissionAnalysisResult` (objectives, target market,
problem, proposed solution, constraints, timeline, success criteria,
assumptions, risks, unknowns, required capabilities) from a mission's raw
text. Two implementations of the ``MissionAnalyzer`` protocol:

- :class:`DeterministicMissionAnalyzer` — rule-based extraction; no model,
  fully reproducible, the default.
- :class:`ModelMissionAnalyzer` — provider-agnostic structured output through
  :class:`app.ai.interfaces.ModelProvider` (used only when a provider is wired).

Analysis output is distilled, auditable knowledge — never raw chain-of-thought.
"""

from __future__ import annotations

import re
from typing import Protocol

from sqlalchemy.orm import Session

from app.ai.interfaces import ModelProvider
from app.core.logging import get_logger
from app.db.models.startup import Mission
from app.startup.types import MissionAnalysisResult

logger = get_logger(__name__)

_BUILD_VERBS = ("build", "create", "develop", "launch", "design", "ship", "make")


class MissionAnalyzer(Protocol):
    """Analyze a mission into structured fields."""

    def analyze(self, mission: Mission) -> MissionAnalysisResult: ...


class DeterministicMissionAnalyzer:
    """Rule-based mission analysis (no model required)."""

    analyzer_name: str = "deterministic"

    def __init__(self, db: Session | None = None) -> None:
        self._db = db

    def analyze(self, mission: Mission) -> MissionAnalysisResult:
        statement = (mission.mission_statement or "").strip()
        market = (mission.target_market or "").strip() or None
        desired = (mission.desired_outcome or "").strip() or None
        constraints = _as_list(mission.constraints)
        assumptions = _as_list(mission.assumptions)
        criteria = _as_list(mission.success_criteria)

        solution = self._extract_solution(statement)
        problem = self._extract_problem(statement)
        timeline = self._extract_timeline(statement, desired)

        objectives = self._build_objectives(
            statement, solution=solution, market=market, desired=desired
        )
        if not criteria:
            criteria = self._default_criteria(desired, solution)
        risks = self._build_risks(market, constraints)
        unknowns = self._build_unknowns(solution, market, criteria, assumptions)

        capabilities = self._build_capabilities(solution, statement)

        return MissionAnalysisResult(
            objectives=objectives,
            target_market=market,
            problem=problem,
            proposed_solution=solution,
            constraints=constraints,
            timeline=timeline,
            success_criteria=criteria,
            assumptions=assumptions,
            risks=risks,
            unknowns=unknowns,
            required_capabilities=capabilities,
            analyzer=self.analyzer_name,
        )

    # ── Extraction rules ───────────────────────────────────────────────

    def _extract_solution(self, statement: str) -> str | None:
        for verb in _BUILD_VERBS:
            pattern = re.compile(rf"^\s*{verb}\s+(.*)$", re.IGNORECASE | re.DOTALL)
            match = pattern.match(statement)
            if match:
                tail = match.group(1).strip().rstrip(".")
                # Strip a trailing " for <market>" propositional phrase.
                tail = re.sub(r"\s+for\s+.+$", "", tail).strip()
                return tail or None
        return None

    def _extract_problem(self, statement: str) -> str | None:
        for marker in ("solve", "address", "help", "enable", "empower"):
            pattern = re.compile(rf"\b{marker}\s+(.*?)(?:[.;]\s|$)", re.IGNORECASE)
            match = pattern.search(statement)
            if match:
                return match.group(1).strip().rstrip(".") or None
        return None

    def _extract_timeline(self, statement: str, desired: str | None) -> str | None:
        text = f"{statement} {desired or ''}".lower()
        quarters = re.findall(r"(\d+[-\s]?)quarters?", text)
        if quarters:
            return f"{quarters[0].strip()} quarters"
        months = re.findall(r"(\d+) months?", text)
        if months:
            return f"{months[0]} months"
        if "next year" in text or "fiscal year" in text:
            return "1 year"
        return None

    def _build_objectives(
        self,
        statement: str,
        *,
        solution: str | None,
        market: str | None,
        desired: str | None,
    ) -> list[str]:
        objectives: list[str] = []
        if solution:
            objectives.append(f"Deliver {solution}")
        if market:
            objectives.append(f"Serve {market}")
        if desired:
            objectives.append(f"Achieve {desired}")
        if not objectives:
            objectives.append(statement.strip().rstrip(".") or "Define and validate the mission")
        return objectives

    def _default_criteria(self, desired: str | None, solution: str | None) -> list[str]:
        criteria: list[str] = []
        if solution:
            criteria.append(f"{solution} ships and is usable by early customers")
        if desired:
            criteria.append(desired)
        criteria.append("Mission milestones are met on the articulated timeline")
        return criteria

    def _build_risks(self, market: str | None, constraints: list[str]) -> list[str]:
        risks: list[str] = []
        if market:
            risks.append(f"Competition and differentiation risk within {market}")
        for constraint in constraints:
            risks.append(f"Constraint pressure: {constraint}")
        risks.append("Scope creep and timeline overruns")
        risks.append("Resource/budget limits constrain delivery")
        return risks

    def _build_unknowns(
        self,
        solution: str | None,
        market: str | None,
        criteria: list[str],
        assumptions: list[str],
    ) -> list[str]:
        unknowns: list[str] = ["Validation data for the assumed problem"]
        if solution:
            unknowns.append(f"Feasibility of building {solution} within constraints")
        if market:
            unknowns.append(f"Willingness of {market} to adopt the solution")
        if not criteria:
            unknowns.append("Measurable success criteria")
        if not assumptions:
            unknowns.append("Explicit assumptions to track and revisit")
        return unknowns

    def _build_capabilities(self, solution: str | None, statement: str) -> list[str]:
        capabilities: list[str] = []
        lowered = statement.lower()
        if solution and any(v in statement.lower() for v in _BUILD_VERBS):
            capabilities.append("product engineering")
        if "ai" in lowered or "intelligence" in lowered or "ml" in lowered:
            capabilities.append("ai / ml engineering")
        if "platform" in lowered or "productivity" in lowered:
            capabilities.append("platform / sdk engineering")
        if "market" in lowered or "go-to-market" in lowered:
            capabilities.append("marketing & go-to-market")
        capabilities.append("operations & delivery")
        return capabilities


class ModelMissionAnalyzer:
    """Provider-agnostic model-backed analysis via structured output."""

    analyzer_name: str = "model"

    def __init__(self, db: Session | None, provider: ModelProvider) -> None:
        self._db = db
        self._provider = provider

    def analyze(self, mission: Mission) -> MissionAnalysisResult:
        from pydantic import BaseModel, Field

        class AnalysisSchema(BaseModel):
            objectives: list[str] = Field(default_factory=list)
            target_market: str | None = None
            problem: str | None = None
            proposed_solution: str | None = None
            constraints: list[str] = Field(default_factory=list)
            timeline: str | None = None
            success_criteria: list[str] = Field(default_factory=list)
            assumptions: list[str] = Field(default_factory=list)
            risks: list[str] = Field(default_factory=list)
            unknowns: list[str] = Field(default_factory=list)
            required_capabilities: list[str] = Field(default_factory=list)

        result = self._provider.structured_output(
            [
                {
                    "role": "user",
                    "content": (
                        "Analyze this startup mission and return structured fields.\n"
                        f"Mission: {mission.mission_statement}\n"
                        f"Target market: {mission.target_market}\n"
                        f"Constraints: {mission.constraints}\n"
                        f"Assumptions: {mission.assumptions}\n"
                        f"Success criteria: {mission.success_criteria}"
                    ),
                }
            ],
            schema=AnalysisSchema,
        )
        return MissionAnalysisResult(
            objectives=list(result.objectives),
            target_market=result.target_market or mission.target_market,
            problem=result.problem,
            proposed_solution=result.proposed_solution,
            constraints=list(result.constraints),
            timeline=result.timeline,
            success_criteria=list(result.success_criteria),
            assumptions=list(result.assumptions),
            risks=list(result.risks),
            unknowns=list(result.unknowns),
            required_capabilities=list(result.required_capabilities),
            analyzer=self.analyzer_name,
        )


def resolve_mission_analyzer(db: Session | None) -> MissionAnalyzer:
    """Select the analyzer implementation from settings.

    Uses :class:`ModelMissionAnalyzer` only when
    ``settings.model_planners_enabled`` is set AND a real provider key is
    configured — otherwise the deterministic (rule-based) analyzer, so the
    offline/demo pipeline never changes by default.
    """
    from app.core.config import settings
    from app.startup.strategy import _real_provider

    if settings.model_planners_enabled:
        provider = _real_provider()
        if provider is not None:
            logger.info("model_mission_analyzer_selected")
            return ModelMissionAnalyzer(db, provider)
        logger.info("model_mission_analyzer_fallback_deterministic")
    return DeterministicMissionAnalyzer(db)


def run_analysis(db: Session, mission: Mission) -> MissionAnalysisResult:
    """Run analysis (model-backed when enabled, else deterministic) and persist."""
    result = resolve_mission_analyzer(db).analyze(mission)
    mission.analysis = __import__("json").dumps(result.to_dict(), default=str)
    db.commit()
    return result


def _as_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    import json

    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(v) for v in value]
    except (json.JSONDecodeError, TypeError):
        pass
    return [line for line in (raw or "").splitlines() if line.strip()]
