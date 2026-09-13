"""Simulation endpoints (Phase 12) — simulations, scenarios, compare, twin.

Runs are isolated sandboxes: all outputs are SIMULATED/FORECAST modeled
estimates — never ACTUAL production data.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import (
    SimulationEvent,
    SimulationMetric,
    SimulationOutcome,
    SimulationScenario,
    SimulationSnapshot,
    SimulationVariable,
)
from app.db.session import get_db  # noqa: B008
from app.phase12._errors import SimulationEngineError
from app.phase12.engine import SimulationEngine
from app.phase12.scenario import ScenarioEngine
from app.phase12.variables import SimulationVariable as SimVar
from app.schemas.phase12 import (
    ScenarioCreate,
    ScenarioPublic,
    SimulationComparisonPublic,
    SimulationCreate,
    SimulationEventPublic,
    SimulationMetricsPublic,
    SimulationPublic,
    SimulationResultsPublic,
    SimulationRunCreate,
    SimulationRunPublic,
    SimulationSnapshotPublic,
    SimulationStatePublic,
    SimulationUpdate,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/simulations", tags=["simulation"])


def _identity_id(identity) -> UUID | None:
    return getattr(identity, "id", None)


def _new_engine(db: Session) -> SimulationEngine:
    return SimulationEngine(db)


def _scenario_dto(vars_rows: list[SimulationVariable]) -> list[SimVar]:
    """Convert persisted variable rows into typed dataclass variables."""
    out: list[SimVar] = []
    for r in vars_rows:
        out.append(
            SimVar(
                name=r.name,
                kind=r.kind,
                value=r.value,
                min_value=r.min_value,
                max_value=r.max_value,
                default=r.default_value,
                description=r.description,
                source=r.source,
                confidence=r.confidence,
            )
        )
    return out


# ── Simulations ──────────────────────────────────────────────────────────────


@router.get("", response_model=list[SimulationPublic], status_code=200)
async def list_simulations(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return [SimulationPublic.model_validate(s) for s in _new_engine(db).list_(company_id)]


@router.post("", response_model=SimulationPublic, status_code=201)
async def create_simulation(
    payload: SimulationCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    engine = _new_engine(db)
    sim = engine.create(
        company_id=payload.company_id,
        name=payload.name,
        description=payload.description,
        scenario_type=payload.scenario_type,
        assumptions=payload.assumptions,
        horizon_days=payload.horizon_days,
        clock_tick=payload.clock_tick,
        created_by=_identity_id(identity),
    )
    if payload.baseline_simulation_id:
        sim.baseline_simulation_id = payload.baseline_simulation_id
        db.commit()
    return SimulationPublic.model_validate(sim)


# Static single-segment GET routes must be registered BEFORE ``/{simulation_id}``:
# FastAPI resolves by registration order, so a literal route registered after the
# UUID param route would be shadowed by it (422 "uuid_parsing").
@router.get("/scenarios", response_model=list[ScenarioPublic], status_code=200)
async def list_scenarios(
    simulation_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    stmt = select(SimulationScenario).order_by(SimulationScenario.created_at.desc())
    if simulation_id is not None:
        stmt = stmt.where(SimulationScenario.simulation_id == simulation_id)
    rows = list(db.execute(stmt).scalars())
    return [ScenarioPublic.model_validate(r) for r in rows]


@router.get("/twin", response_model=list[SimulationSnapshotPublic], status_code=200)
async def list_snapshots(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    stmt = select(SimulationSnapshot).order_by(SimulationSnapshot.created_at.desc())
    if company_id is not None:
        stmt = stmt.where(SimulationSnapshot.company_id == company_id)
    rows = list(db.execute(stmt).scalars())
    return [SimulationSnapshotPublic.model_validate(r) for r in rows]


@router.get("/{simulation_id}", response_model=SimulationPublic, status_code=200)
async def get_simulation(
    simulation_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    sim = _new_engine(db).get(simulation_id)
    if sim is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Simulation not found")
    return SimulationPublic.model_validate(sim)


@router.put("/{simulation_id}", response_model=SimulationPublic, status_code=200)
async def update_simulation(
    simulation_id: UUID,
    payload: SimulationUpdate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    sim = _new_engine(db).get(simulation_id)
    if sim is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Simulation not found")
    if payload.name is not None:
        sim.name = payload.name
    if payload.description is not None:
        sim.description = payload.description
    if payload.assumptions is not None:
        sim.assumptions_json = payload.assumptions
    if payload.horizon_days is not None:
        sim.horizon_days = payload.horizon_days
    if payload.clock_tick is not None:
        sim.clock_tick = payload.clock_tick
    db.commit()
    return SimulationPublic.model_validate(sim)


@router.post("/{simulation_id}/run", response_model=SimulationRunPublic, status_code=201)
async def run_simulation(
    simulation_id: UUID,
    payload: SimulationRunCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    engine = _new_engine(db)
    scenario_vars: list[SimVar] = []
    if payload.scenario_id:
        rows = list(
            db.execute(
                select(SimulationVariable).where(
                    SimulationVariable.scenario_id == payload.scenario_id
                )
            ).scalars()
        )
        scenario_vars = _scenario_dto(rows)
    run = engine.run(
        simulation_id=simulation_id,
        scenario_id=payload.scenario_id,
        seed=payload.seed,
        iterations=payload.iterations,
        variables=scenario_vars,
    )
    return SimulationRunPublic.model_validate(run)


@router.post("/runs/{run_id}/pause", response_model=SimulationRunPublic, status_code=200)
async def pause_run(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return SimulationRunPublic.model_validate(_new_engine(db).pause(run_id))


@router.post("/runs/{run_id}/cancel", response_model=SimulationRunPublic, status_code=200)
async def cancel_run(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return SimulationRunPublic.model_validate(_new_engine(db).cancel(run_id))


@router.get("/runs/{run_id}", response_model=SimulationRunPublic, status_code=200)
async def get_run(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    try:
        run = _new_engine(db).get_run(run_id)
    except SimulationEngineError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SimulationRunPublic.model_validate(run)


@router.get("/runs/{run_id}/state", response_model=SimulationStatePublic, status_code=200)
async def run_state(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    try:
        state = _new_engine(db).run_state(run_id)
    except SimulationEngineError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SimulationStatePublic.model_validate(state)


@router.get("/runs/{run_id}/events", response_model=list[SimulationEventPublic], status_code=200)
async def run_events(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rows = list(
        db.execute(
            select(SimulationEvent)
            .where(SimulationEvent.run_id == run_id)
            .order_by(SimulationEvent.tick)
            .limit(500)
        ).scalars()
    )
    return [SimulationEventPublic.model_validate(r) for r in rows]


@router.get("/runs/{run_id}/metrics", response_model=SimulationMetricsPublic, status_code=200)
async def run_metrics(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rows = list(
        db.execute(select(SimulationMetric).where(SimulationMetric.run_id == run_id)).scalars()
    )
    return SimulationMetricsPublic(
        run_id=run_id,
        metrics=[{"key": m.key, "value": m.value, "tick": m.tick} for m in rows],
    )


@router.get("/runs/{run_id}/results", response_model=SimulationResultsPublic, status_code=200)
async def run_results(
    run_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    try:
        run = _new_engine(db).get_run(run_id)
    except SimulationEngineError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    outcomes = list(
        db.execute(select(SimulationOutcome).where(SimulationOutcome.run_id == run_id)).scalars()
    )
    summary = run.summary_json or {}
    metrics: list[dict] = summary.get("metrics", {})
    return SimulationResultsPublic(
        run_id=run_id,
        iterations=int(summary.get("iterations", 1)),
        summary_json=summary,
        metrics=[
            {"key": k, "value": v["mean"], "min": v["min"], "max": v["max"]}
            for k, v in metrics.items()
        ],
        outcomes=[
            {"metric_key": o.metric_key, "value": o.value, "kind": o.output_kind} for o in outcomes
        ],
    )


# ── Scenarios ─────────────────────────────────────────────────────────────────


@router.post("/scenarios", response_model=ScenarioPublic, status_code=201)
async def create_scenario(
    payload: ScenarioCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    # Validate via ScenarioEngine (types + bounds) before persisting anything.
    vars_dto = []
    for v in payload.variables:
        vars_dto.append(
            SimVar(
                name=v.name,
                kind=v.kind,
                value=v.value,
                min_value=v.min_value,
                max_value=v.max_value,
                default=v.default_value,
                description=v.description,
                source=v.source,
                confidence=v.confidence,
            )
        )
    ScenarioEngine().build(
        name=payload.name,
        scenario_type=payload.scenario_type,
        simulation_id=payload.simulation_id,
        company_id=payload.company_id,
        description=payload.description,
        assumptions=payload.assumptions,
        horizon_days=payload.horizon_days,
        variables=vars_dto,
        objectives=payload.objective,
        is_baseline=payload.is_baseline,
    )
    row = SimulationScenario(
        simulation_id=payload.simulation_id,
        company_id=payload.company_id,
        name=payload.name,
        scenario_type=payload.scenario_type,
        description=payload.description,
        assumptions_json=payload.assumptions,
        horizon_days=payload.horizon_days,
        objective_json=payload.objective,
        is_baseline=payload.is_baseline,
        created_by=_identity_id(identity),
    )
    db.add(row)
    db.flush()  # materialize row.id for variable rows
    for _i, v in enumerate(payload.variables):
        db.add(
            SimulationVariable(
                simulation_id=payload.simulation_id,
                scenario_id=row.id,
                company_id=payload.company_id,
                name=v.name,
                kind=v.kind,
                value=v.value,
                min_value=v.min_value,
                max_value=v.max_value,
                default_value=v.default_value,
                description=v.description,
                source=v.source,
                confidence=v.confidence,
            )
        )
    db.commit()
    return ScenarioPublic.model_validate(row)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioPublic, status_code=200)
async def get_scenario(
    scenario_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    row = db.get(SimulationScenario, scenario_id)
    if row is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Scenario not found")
    return ScenarioPublic.model_validate(row)


@router.post("/scenarios/{scenario_id}/run", response_model=SimulationRunPublic, status_code=201)
async def run_scenario(
    scenario_id: UUID,
    payload: SimulationRunCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    scenario = db.get(SimulationScenario, scenario_id)
    if scenario is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Scenario not found")
    rows = list(
        db.execute(
            select(SimulationVariable).where(SimulationVariable.scenario_id == scenario_id)
        ).scalars()
    )
    run = _new_engine(db).run(
        simulation_id=scenario.simulation_id,
        scenario_id=scenario_id,
        seed=payload.seed,
        iterations=payload.iterations,
        variables=_scenario_dto(rows),
    )
    return SimulationRunPublic.model_validate(run)


@router.post(
    "/compare/runs",
    response_model=SimulationComparisonPublic,
    status_code=201,
)
async def compare_runs(
    payload: dict,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    baseline_run_id = payload.get("baseline_run_id")
    scenario_run_id = payload.get("scenario_run_id")
    if not baseline_run_id or not scenario_run_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="baseline_run_id and scenario_run_id are required",
        )
    comp = _new_engine(db).compare(
        baseline_run_id=UUID(str(baseline_run_id)),
        scenario_run_id=UUID(str(scenario_run_id)),
    )
    return SimulationComparisonPublic.model_validate(comp)


# ── Digital twin ──────────────────────────────────────────────────────────────


@router.post("/twin", response_model=SimulationSnapshotPublic, status_code=201)
async def snapshot_twin(
    payload: dict,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from fastapi import HTTPException

    from app.phase12.digital_twin import CompanyDigitalTwin, DigitalTwinError

    company_id = payload.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id is required")
    try:
        snap = CompanyDigitalTwin(
            name=payload.get("name", "nexus-twin-v1"),
            model_version=payload.get("model_version", "1.0"),
        ).snapshot(db, UUID(str(company_id)), created_by=_identity_id(identity))
    except DigitalTwinError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SimulationSnapshotPublic.model_validate(snap)


__all__ = ["router"]
