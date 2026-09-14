"""Item 8 — Configurable model-backed startup analyzers/planners.

``MODEL_PLANNERS_ENABLED`` (default off) routes mission analysis + strategic
planning through the model-backed implementations when a real provider key is
present; otherwise — flag off *or* keyless — the deterministic rule-based
pipeline is used unchanged. These tests lock in the selection matrix.
"""

from __future__ import annotations

from app.core.config import settings
from app.startup.analyze import DeterministicMissionAnalyzer, resolve_mission_analyzer
from app.startup.strategy import (
    DeterministicStrategicPlanner,
    ModelStrategicPlanner,
    resolve_strategic_planner,
)


class _FakeProvider:
    """Deterministic structured-output provider returning tagged content.

    Schema-aware: the analysis schema wants string objectives, the strategy
    schema wants dict objectives — mirror the real contracts.
    """

    def structured_output(self, messages, *, schema, options=None):  # noqa: ANN001, ARG002
        if schema.__name__ == "AnalysisSchema":
            return schema.model_validate(
                {
                    "objectives": ["obj-1", "obj-2"],
                    "proposed_solution": "model solution",
                    "target_market": "model market",
                }
            )
        return schema.model_validate(
            {
                "vision": "Model-backed vision",
                "objectives": [{"title": "obj-1", "id": "1"}],
                "priorities": ["model priority"],
                "success_metrics": ["model metric"],
                "capabilities": ["model capability"],
            }
        )


# ── config ─────────────────────────────────────────────────────────────────


def test_model_planners_default_off():
    assert settings.model_planners_enabled is False


# ── resolve_strategic_planner selection matrix ─────────────────────────────


def test_planner_deterministic_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "model_planners_enabled", False)
    planner = resolve_strategic_planner(None)
    assert isinstance(planner, DeterministicStrategicPlanner)


def test_planner_deterministic_when_flag_on_but_no_provider(monkeypatch):
    monkeypatch.setattr(settings, "model_planners_enabled", True)
    monkeypatch.setattr("app.startup.strategy._real_provider", lambda: None)
    planner = resolve_strategic_planner(None)
    assert isinstance(planner, DeterministicStrategicPlanner)


def test_planner_model_when_flag_on_with_provider(monkeypatch):
    monkeypatch.setattr(settings, "model_planners_enabled", True)
    monkeypatch.setattr("app.startup.strategy._real_provider", lambda: _FakeProvider())
    planner = resolve_strategic_planner(None)
    assert isinstance(planner, ModelStrategicPlanner)


def test_model_planner_plan_uses_provider_output(monkeypatch):
    from app.startup.strategy import ModelStrategicPlanner

    planner = ModelStrategicPlanner(None, _FakeProvider())
    plan = planner.plan(mission=_mission(), analysis=_analysis())
    assert plan.vision == "Model-backed vision"
    assert plan.success_metrics == ["model metric"]


# ── resolve_mission_analyzer selection matrix ──────────────────────────────


def test_analyzer_deterministic_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "model_planners_enabled", False)
    analyzer = resolve_mission_analyzer(None)
    assert isinstance(analyzer, DeterministicMissionAnalyzer)


def test_analyzer_deterministic_when_flag_on_but_no_provider(monkeypatch):
    monkeypatch.setattr(settings, "model_planners_enabled", True)
    monkeypatch.setattr("app.startup.strategy._real_provider", lambda: None)
    analyzer = resolve_mission_analyzer(None)
    assert isinstance(analyzer, DeterministicMissionAnalyzer)


def test_analyzer_model_when_flag_on_with_provider(monkeypatch):
    monkeypatch.setattr(settings, "model_planners_enabled", True)
    monkeypatch.setattr("app.startup.strategy._real_provider", lambda: _FakeProvider())
    analyzer = resolve_mission_analyzer(None)
    assert analyzer.__class__.__name__ == "ModelMissionAnalyzer"


# ── end-to-end through MissionManager (flag on + provider) ─────────────────


def test_mission_analyze_uses_model_analyzer(monkeypatch, db):
    from app.startup.mission import MissionManager
    from tests.test_startup_mission import _company, _mission_payload

    company = _company(db)
    mission = MissionManager(db).create(company_id=company.id, **_mission_payload())

    monkeypatch.setattr(settings, "model_planners_enabled", True)
    monkeypatch.setattr("app.startup.strategy._real_provider", lambda: _FakeProvider())

    result = MissionManager(db).analyze(mission)
    assert result.analyzer == "model"
    assert result.proposed_solution == "model solution"


def test_mission_plan_persists_model_strategy(monkeypatch, db):
    from sqlalchemy import select

    from app.db.models.startup import StrategicPlan
    from app.startup.mission import MissionManager
    from tests.test_startup_mission import _company, _mission_payload

    company = _company(db)
    mission = MissionManager(db).create(company_id=company.id, **_mission_payload())

    monkeypatch.setattr(settings, "model_planners_enabled", True)
    monkeypatch.setattr("app.startup.strategy._real_provider", lambda: _FakeProvider())

    MissionManager(db).plan(mission)
    strategy = db.scalar(select(StrategicPlan).where(StrategicPlan.mission_id == mission.id))
    assert strategy is not None
    # the strategic plan row carries the model-backed vision verbatim
    assert strategy.vision == "Model-backed vision"


# ── fixtures ───────────────────────────────────────────────────────────────


def _mission():
    from app.db.models.startup import Mission

    return Mission(
        title="M",
        mission_statement="Build a deterministic test mission.",
        target_market="test market",
    )


def _analysis():
    from app.startup.types import MissionAnalysisResult

    return MissionAnalysisResult(
        objectives=["obj-1"],
        target_market="test market",
        problem="test problem",
        proposed_solution="test solution",
        success_criteria=["metric"],
        analyzer="deterministic",
    )
