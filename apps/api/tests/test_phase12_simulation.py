"""Phase 12 simulation engine + digital twin tests (§60)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.company.manager import CompanyManager
from app.db.models.phase12 import SimulationIteration, SimulationRun
from app.phase12._errors import SimulationEngineError
from app.phase12._types import SimVariableKind
from app.phase12.digital_twin import CompanyDigitalTwin, DigitalTwinError
from app.phase12.engine import SimulationEngine
from app.phase12.variables import (
    SimulationVariable,
    VariableValidationError,
    validate_variables,
)


def _make_company(db):
    return CompanyManager(db).create(name="Sim Co")


def _assert_validation_error(var: SimulationVariable) -> None:
    with pytest.raises(VariableValidationError):
        var.validate()


# ── Simulation creation & defaults ───────────────────────────────────────────


def test_create_simulation_defaults(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    sim = engine.create(company_id=company.id, name="Defaults sim")
    assert sim.status == "draft"
    assert sim.sandboxed is True
    assert sim.scenario_type == "custom"
    assert sim.clock_tick == "day"
    assert sim.model_name == "nexus-v1-default"
    assert sim.model_version == "1.0"
    runs = list(
        db.execute(select(SimulationRun).where(SimulationRun.simulation_id == sim.id)).scalars()
    )
    assert runs == []


# ── Variable validation ──────────────────────────────────────────────────────


def test_validation_rejects_out_of_bounds_variable(db):
    _assert_validation_error(
        SimulationVariable("budget", SimVariableKind.INTEGER, min_value=1, max_value=10, value=50)
    )
    _assert_validation_error(
        SimulationVariable(
            "headcount", SimVariableKind.INTEGER, min_value=10, max_value=100, value=5
        )
    )
    _assert_validation_error(
        SimulationVariable("env", SimVariableKind.ENUM, value="staging", options=["prod", "dev"])
    )
    _assert_validation_error(SimulationVariable("alloc", SimVariableKind.PERCENTAGE, value=150))
    # String booleans ("yes"/"true"/"on") are coerced to bool by design, so the
    # BOOLEAN guard is exercised with a genuinely non-bool value.
    _assert_validation_error(SimulationVariable("flag", SimVariableKind.BOOLEAN, value=1))


def test_validate_variables_batch(db):
    good = [
        SimulationVariable(
            "headcount", SimVariableKind.INTEGER, value=5, min_value=1, max_value=50
        ),
        SimulationVariable("budget", SimVariableKind.FLOAT, value=2500.0, min_value=0.0),
        SimulationVariable("env", SimVariableKind.ENUM, value="prod", options=["prod", "dev"]),
        SimulationVariable("alloc", SimVariableKind.PERCENTAGE, value=60),
        SimulationVariable("flag", SimVariableKind.BOOLEAN, value=True),
    ]
    assert validate_variables(good)
    with pytest.raises(VariableValidationError):
        validate_variables(
            [
                SimulationVariable(
                    "budget", SimVariableKind.INTEGER, min_value=1, max_value=10, value=50
                )
            ]
        )


# ── Deterministic runs ───────────────────────────────────────────────────────


def test_run_deterministic_and_completed(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    sim = engine.create(
        company_id=company.id, name="Det sim", scenario_type="what_if", horizon_days=30
    )
    run = engine.run(
        simulation_id=sim.id,
        iterations=1,
        seed="det-1",
        variables=[SimulationVariable("headcount", SimVariableKind.INTEGER, value=5)],
    )
    assert run.status == "completed"
    assert run.tick_count == 30
    assert run.summary_json["iterations"] == 1
    assert set(run.summary_json["metrics"]) >= {"utilization", "capacity", "completed_tasks"}


def test_seeded_stochastic_reproducible(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    variables = [SimulationVariable("headcount", SimVariableKind.INTEGER, value=5)]
    sim_a = engine.create(company_id=company.id, name="Repro A", horizon_days=30)
    run_a = engine.run(simulation_id=sim_a.id, iterations=1, seed="rep-1", variables=variables)
    sim_b = engine.create(company_id=company.id, name="Repro B", horizon_days=30)
    run_b = engine.run(simulation_id=sim_b.id, iterations=1, seed="rep-1", variables=variables)
    assert run_a.status == "completed"
    assert run_b.status == "completed"
    assert run_a.summary_json["metrics"] == run_b.summary_json["metrics"]


# ── Run state & isolation ────────────────────────────────────────────────────


def test_state_isolation_two_simulations(db):
    engine = SimulationEngine(db)
    company_a = CompanyManager(db).create(name="Isolate A")
    company_b = CompanyManager(db).create(name="Isolate B")
    sim_a = engine.create(company_id=company_a.id, name="iso-a", horizon_days=3)
    sim_b = engine.create(company_id=company_b.id, name="iso-b", horizon_days=8)
    run_a = engine.run(simulation_id=sim_a.id, iterations=1, seed="iso-a")
    run_b = engine.run(simulation_id=sim_b.id, iterations=1, seed="iso-b")
    state_a = engine.run_state(run_a.id)
    state_b = engine.run_state(run_b.id)
    assert state_a["simulation_id"] == str(sim_a.id)
    assert state_b["simulation_id"] == str(sim_b.id)
    assert state_a["simulation_id"] != state_b["simulation_id"]
    assert state_a["events"] != state_b["events"]
    assert all(e["kind"] for e in state_a["events"])
    assert all(e["kind"] for e in state_b["events"])


def test_clock_ticks_progress(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    sim = engine.create(company_id=company.id, name="Clock sim", horizon_days=10)
    run = engine.run(simulation_id=sim.id, iterations=1, seed="clock")
    state = engine.run_state(run.id)
    assert state["tick"] >= 1
    assert state["tick"] == 10


def test_events_recorded(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    sim = engine.create(company_id=company.id, name="Events sim", horizon_days=3)
    run = engine.run(simulation_id=sim.id, iterations=1, seed="events")
    state = engine.run_state(run.id)
    assert state["events"]
    for event in state["events"]:
        assert isinstance(event["tick"], int)
        assert event["kind"]
    kinds = {event["kind"] for event in state["events"]}
    assert "task_completed" in kinds


# ── Checkpoints, cancel & restore ────────────────────────────────────────────


def test_checkpoint_and_restore(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    sim = engine.create(company_id=company.id, name="Cp sim", horizon_days=10)
    run = engine.run(simulation_id=sim.id, iterations=1, seed="cp")
    assert run.status == "completed"
    cp = engine.checkpoint(run.id, tag="mid")
    assert cp.action == "checkpoint"
    assert cp.tick == run.tick_count
    restored = engine.restore(run.id, cp.id)
    assert restored.status == "ready"


def test_cancel_completed_run_rejected(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    sim = engine.create(company_id=company.id, name="Cancel completed", horizon_days=5)
    run = engine.run(simulation_id=sim.id, iterations=1, seed="done")
    assert run.status == "completed"
    with pytest.raises(SimulationEngineError):
        engine.cancel(run.id)


def test_cancel_ready_run(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    sim = engine.create(company_id=company.id, name="Cancel ready", horizon_days=5)
    engine.ready(sim.id)
    run = engine.run(simulation_id=sim.id, iterations=1, seed="ready")
    cp = engine.checkpoint(run.id)
    engine.restore(run.id, cp.id)  # sets the run back to READY
    cancelled = engine.cancel(run.id)
    assert cancelled.status == "cancelled"


# ── Resource governance ──────────────────────────────────────────────────────


def test_max_ticks_caps_horizon(db):
    company = _make_company(db)
    engine = SimulationEngine(db, max_ticks=5)
    sim = engine.create(company_id=company.id, name="Capped sim", horizon_days=200)
    run = engine.run(simulation_id=sim.id, iterations=1, seed="cap")
    assert run.status == "completed"
    assert run.tick_count == 5


def test_timeout_fails_run(db):
    company = _make_company(db)
    engine = SimulationEngine(db, run_timeout_seconds=0.0)
    sim = engine.create(company_id=company.id, name="Timeout sim", horizon_days=5)
    run = engine.run(simulation_id=sim.id, iterations=2, seed="timeout")
    assert run.status == "failed"
    assert "timeout" in run.error_message


def test_resource_limit_event_budget(db):
    company = _make_company(db)
    engine = SimulationEngine(db, max_events=1)
    sim = engine.create(company_id=company.id, name="Event budget sim", horizon_days=5)
    run = engine.run(simulation_id=sim.id, iterations=1, seed="events")
    assert run.status == "failed"
    assert "event budget" in run.error_message


# ── Comparisons ──────────────────────────────────────────────────────────────


def test_baseline_comparison(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    base = engine.create(
        company_id=company.id, name="Baseline", scenario_type="baseline", horizon_days=30
    )
    scenario = engine.create(
        company_id=company.id, name="Scenario", scenario_type="what_if", horizon_days=30
    )
    base_run = engine.run(
        simulation_id=base.id,
        iterations=1,
        seed="base",
        variables=[SimulationVariable("headcount", SimVariableKind.INTEGER, value=5)],
    )
    scenario_run = engine.run(
        simulation_id=scenario.id,
        iterations=1,
        seed="scen",
        variables=[SimulationVariable("headcount", SimVariableKind.INTEGER, value=10)],
    )
    comp = engine.compare(baseline_run_id=base_run.id, scenario_run_id=scenario_run.id)
    assert comp.metric_deltas_json
    for delta in comp.metric_deltas_json.values():
        assert "baseline" in delta
        assert "scenario" in delta
        assert "delta" in delta
    self_comp = engine.compare(baseline_run_id=base_run.id, scenario_run_id=base_run.id)
    assert self_comp.metric_deltas_json
    assert all(abs(delta["delta"]) == 0.0 for delta in self_comp.metric_deltas_json.values())


# ── Multi-run aggregation ────────────────────────────────────────────────────


def test_multi_run_aggregates(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    sim = engine.create(company_id=company.id, name="Multi sim", horizon_days=10)
    run = engine.run(simulation_id=sim.id, iterations=3, seed="multi")
    assert run.status == "completed"
    assert run.summary_json["iterations"] == 3
    for metric in run.summary_json["metrics"].values():
        assert "min" in metric
        assert "max" in metric
        assert "mean" in metric
        assert "median" in metric
    iterations = list(
        db.execute(
            select(SimulationIteration).where(SimulationIteration.run_id == run.id)
        ).scalars()
    )
    assert {row.iteration for row in iterations} == {1, 2, 3}


# ── Digital twin ─────────────────────────────────────────────────────────────


def test_digital_twin_snapshot(db):
    company = _make_company(db)
    twin = CompanyDigitalTwin()
    snap = twin.snapshot(db, company.id)
    data = snap.snapshot_json
    assert data["company"]["name"] == company.name
    assert isinstance(data["counts"], dict)
    assert data["disclaimer"]


def test_digital_twin_missing_company(db):
    twin = CompanyDigitalTwin()
    with pytest.raises(DigitalTwinError):
        twin.snapshot(db, uuid4())


# ── Variables drive the scenario ─────────────────────────────────────────────


def test_variables_drive_scenario(db):
    company = _make_company(db)
    engine = SimulationEngine(db)
    sim = engine.create(company_id=company.id, name="Vars sim", horizon_days=5)
    run = engine.run(
        simulation_id=sim.id, iterations=1, seed="vars", baseline_values={"throughput": 5.0}
    )
    assert run.status == "completed"
    metric_keys = {metric["key"] for metric in engine.run_state(run.id)["metrics"]}
    assert "kpi_throughput" in metric_keys
