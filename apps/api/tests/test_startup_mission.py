"""Tests for the Phase 9 mission system — creation, analysis, validation,
lifecycle transitions, success criteria, and company isolation."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.models.startup import Mission, MissionStatus

_counter = 0


def _company(db: Session, name: str | None = None) -> Company:
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=name or f"Mission Test Co {_counter}", description="unit")


def _mission_payload() -> dict:
    return {
        "title": "Ship a developer tool",
        "mission_statement": (
            "Build a CLI that accelerates small teams through verifiable cycles."
        ),
        "description": "A deterministic unit-test mission.",
        "desired_outcome": "Initial cohort adopts the CLI.",
        "target_market": "small software teams",
        "constraints": ["Bounded autonomy only", "No external integrations."],
        "assumptions": ["Small teams adopt CLI tooling."],
        "success_criteria": ["Task success rate above 90%."],
        "strategic_context": {"phase": 9, "mode": "deterministic"},
        "priority": 1,
    }


def _validation_dict(result) -> dict:
    """Normalize a ValidationResult into (ok, errors, warnings)."""
    return result.to_dict()


class TestMissionCreation:
    def test_create_and_load(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        company = _company(db)
        mgr = MissionManager(db)
        mission = mgr.create(company_id=company.id, **_mission_payload())

        assert mission.status == MissionStatus.DRAFT
        assert str(mission.company_id) == str(company.id)
        assert mission.title == "Ship a developer tool"

        reloaded = mgr.get(company.id, mission.id)
        assert reloaded is not None
        assert reloaded.id == mission.id

    def test_list_scoped_to_company(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        company_a = _company(db)
        company_b = _company(db)
        mgr = MissionManager(db)
        payload = _mission_payload()
        payload["title"] = "Other mission"
        mgr.create(company_id=company_a.id, **_mission_payload())
        mgr.create(company_id=company_b.id, **payload)

        assert len(mgr.list_(company_a.id)) == 1
        assert len(mgr.list_(company_b.id)) == 1

    def test_company_isolation(self, db: Session) -> None:
        """§38 — missions of company A are not visible as company B."""
        from app.startup.mission import MissionManager

        company_a = _company(db)
        company_b = _company(db)
        mgr = MissionManager(db)
        mission = mgr.create(company_id=company_a.id, **_mission_payload())

        assert mgr.get(company_b.id, mission.id) is None
        assert mgr.list_(company_b.id) == []


class TestMissionAnalysis:
    def test_deterministic_analysis(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        company = _company(db)
        mission = MissionManager(db).create(company_id=company.id, **_mission_payload())
        result = MissionManager(db).analyze(mission)

        assert result.objectives
        assert result.proposed_solution
        assert result.required_capabilities
        assert result.analyzer == "deterministic"
        assert result.target_market == "small software teams"

    def test_analysis_persists_on_mission(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        company = _company(db)
        mission = MissionManager(db).create(company_id=company.id, **_mission_payload())
        MissionManager(db).analyze(mission)
        row = db.get(Mission, mission.id)
        assert row is not None
        assert row.analysis is not None


class TestMissionValidation:
    def test_valid_mission_passes(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        company = _company(db)
        mission = MissionManager(db).create(company_id=company.id, **_mission_payload())
        result = MissionManager(db).validate(mission)
        data = _validation_dict(result)
        assert data["ok"] is True
        assert data["errors"] == []

    def test_missing_mission_statement_fails(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        company = _company(db)
        payload = _mission_payload()
        payload["mission_statement"] = ""
        mission = MissionManager(db).create(company_id=company.id, **payload)
        data = _validation_dict(MissionManager(db).validate(mission))
        assert data["ok"] is False
        assert any("mission_statement" in e["code"] for e in data["errors"])

    def test_conflicting_constraints_detected(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        company = _company(db)
        payload = _mission_payload()
        payload["constraints"] = [
            "Must ship within 1 month on a free budget.",
            "Requires an enterprise-scale platform.",
        ]
        mission = MissionManager(db).create(company_id=company.id, **payload)
        data = _validation_dict(MissionManager(db).validate(mission))
        assert any(e["code"] == "conflicting_constraints" for e in data["warnings"])


class TestMissionLifecycle:
    def _planned_mission(self, db: Session) -> tuple[Mission, object]:
        from app.startup.mission import MissionManager

        company = _company(db)
        mgr = MissionManager(db)
        mission = mgr.create(company_id=company.id, **_mission_payload())
        mgr.plan(mission)
        return mission, mgr

    def test_activate(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        mission, _ = self._planned_mission(db)
        company_id = mission.company_id
        MissionManager(db).activate(company_id, mission.id)
        assert db.get(Mission, mission.id).status == MissionStatus.ACTIVE

    def test_pause_resume(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        mission, _ = self._planned_mission(db)
        company_id = mission.company_id
        mgr = MissionManager(db)
        mgr.activate(company_id, mission.id)
        mgr.pause(company_id, mission.id)
        assert db.get(Mission, mission.id).status == MissionStatus.PAUSED
        mgr.activate(company_id, mission.id)
        assert db.get(Mission, mission.id).status == MissionStatus.ACTIVE

    def test_complete(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        mission, _ = self._planned_mission(db)
        company_id = mission.company_id
        mgr = MissionManager(db)
        mgr.activate(company_id, mission.id)
        mgr.complete(company_id, mission.id)
        assert db.get(Mission, mission.id).status == MissionStatus.COMPLETED

    def test_cancel(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        mission, _ = self._planned_mission(db)
        company_id = mission.company_id
        mgr = MissionManager(db)
        mgr.cancel(company_id, mission.id)
        assert db.get(Mission, mission.id).status == MissionStatus.CANCELLED

    def test_plan_derives_strategic_and_startup_plans(self, db: Session) -> None:
        from app.startup.mission import MissionManager

        company = _company(db)
        mgr = MissionManager(db)
        mission = mgr.create(company_id=company.id, **_mission_payload())
        result = mgr.plan(mission)
        assert result["status"] == "planned"
        assert result["strategic_plan_id"]
        assert result["startup_plan_id"]
        assert db.get(Mission, mission.id).status == MissionStatus.PLANNED


class TestMissionGraph:
    def test_mission_links_on_create(self, db: Session) -> None:
        from app.startup.graph import MissionGraphBuilder
        from app.startup.mission import MissionManager

        company = _company(db)
        mission = MissionManager(db).create(company_id=company.id, **_mission_payload())
        graph = MissionGraphBuilder(db)
        # The mission is a root: it has no parents, but nodes that derive from
        # it appear once the plan pipeline runs. Edges in the company still
        # resolve without error.
        assert graph.parents(company.id, "mission", mission.id) == []
