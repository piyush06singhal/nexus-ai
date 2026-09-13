"""SimulationEngine — lifecycle, isolated execution, multi-run, checkpointing.

Lifecycle state machine: DRAFT → READY → RUNNING → (PAUSED ⇄ RUNNING) →
COMPLETED / FAILED / CANCELLED.

Execution is isolated: the engine materialises a *sandbox context* (clock,
events, variables, behavior) and steps it tick by tick. It never touches
production data — all output is stored as SIMULATED/FORECAST rows.

- Multi-run: one run may hold N iterations (seed-per-iteration, seed string),
  producing min/max/mean/median/percentiles aggregated in the run summary.
- ``SimulationComparison``: baseline vs scenario (metric deltas, bottlenecks).
- ``SimulationCheckpoint``: checkpoint / resume / restore for long runs.
- Cancellation + timeouts + event/entity budgets are enforced per run
  (resource governance).
"""

from __future__ import annotations

import datetime as _dt
import statistics
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import (
    SimCheckpointAction,
    SimStatus,
    Simulation,
    SimulationCheckpoint,
    SimulationComparison,
    SimulationEvent,
    SimulationIteration,
    SimulationMetric,
    SimulationOutcome,
    SimulationOutputKind,
    SimulationRun,
)
from app.phase12._errors import SimulationEngineError, SimulationSandboxRefusalError
from app.phase12.behavior import AgentBehaviorModel
from app.phase12.events import SimEvent, SimulationEventLog
from app.phase12.events import SimEventKind as Kinds
from app.phase12.governance import ConcurrentRunGate, Phase12RunBudget
from app.phase12.scenario import Scenario
from app.phase12.sim_clock import SimulationClock
from app.phase12.simulators import (
    BudgetSimulator,
    KpiSimulator,
    RiskSimulator,
    WorkforceSimulator,
)
from app.phase12.variables import SimulationVariable

_DEFAULT_MODEL = AgentBehaviorModel()


class SimulationSandbox:
    """In-memory state for a single running simulation. Nothing here mutates
    production data — it is a closed sandbox."""

    def __init__(
        self,
        *,
        scenario: Scenario,
        model: AgentBehaviorModel | None = None,
        company_id: UUID | None = None,
        baseline_values: dict[str, float] | None = None,
    ) -> None:
        self.scenario = scenario
        self.model = model or _DEFAULT_MODEL
        self.company_id = company_id
        self.clock = SimulationClock(resolution="day")
        if scenario.horizon_days:
            self.horizon = scenario.horizon_days
        else:
            self.horizon = 30
        self.events = SimulationEventLog()
        self.entities: dict[str, dict[str, Any]] = {}
        self.workforce = WorkforceSimulator(
            headcount=self._variable_int("headcount", 5), behavior=self.model
        )
        self.budget_sim = BudgetSimulator(
            budget=self._variable_float("budget", 1000.0),
            spent=self._variable_float("spent", 0.0),
            behavior=self.model,
        )
        self.kpi_sim = KpiSimulator(baseline_values=baseline_values or {})
        self.risk = RiskSimulator()
        self.metrics: dict[str, list[float]] = {}
        self._task_in_flight = 0
        self._completed = 0
        self._failed = 0
        # Zero-outbound boundary: behaviors call ``refuse`` before any
        # would-be production/external side effect; the sim is closed.
        self._boundary_breached = False
        self._refusals: list[SimEvent] = []

    def _variable_int(self, name: str, default: int) -> int:
        for v in self.scenario.variables:
            if v.name == name:
                n = v.as_number
                return int(n) if n is not None else default
        return default

    def refuse(self, kind: str, detail: dict[str, Any] | None = None) -> None:
        """Refuse a production/external side effect and mark the sim as failed.

        Raises :class:`SimulationSandboxRefusalError` so the run is failed with
        an honest message; the refusal is also recorded as a sim event (inside
        the sim only — never an external action).
        """
        self._boundary_breached = True
        event = SimEvent(tick=self.clock.tick, kind=Kinds.SANDBOX_REFUSAL, detail=detail or {})
        self._refusals.append(event)
        self.events.record(event)
        raise SimulationSandboxRefusalError(
            f"Simulation refused external/production side effect: {kind}"
        )

    def _variable_float(self, name: str, default: float) -> float:
        for v in self.scenario.variables:
            if v.name == name:
                n = v.as_number
                return float(n) if n is not None else default
        return default

    # ── Stepping ──────────────────────────────────────────────────────

    def step(self, tick: int) -> None:
        """Advance one tick of modeled work."""
        due = self.clock.due(tick)
        for ev in due:
            self.events.record(
                SimEvent(tick=tick, kind=ev.kind, entity_ref=ev.entity_ref, detail=ev.payload or {})
            )
        # Modeled task inflow: 1 work unit per tick, latency-scored.
        work_units = 1.0
        self._task_in_flight += 1
        work_completes = work_units / max(1, self.model.latency_ticks())
        completed_now = 1 if self._task_in_flight > 0 else 0
        self._task_in_flight = max(0, self._task_in_flight - completed_now)
        if self.model.stochastic:
            if self.model.failed():
                self._failed += 1
                self.events.record(SimEvent(tick=tick, kind=Kinds.TASK_FAILED, severity="warning"))
            else:
                self._completed += 1
                self.events.record(SimEvent(tick=tick, kind=Kinds.TASK_COMPLETED))
        else:
            self._completed += 1
            self.events.record(SimEvent(tick=tick, kind=Kinds.TASK_COMPLETED))
        # Metrics.
        util = self.workforce.utilization(self._task_in_flight + work_completes)
        self._record_metric("utilization", util)
        self._record_metric("capacity", self.workforce.total_capacity())
        self._record_metric("completed_tasks", float(self._completed))
        self._record_metric("cost", float(self.budget_sim.projected_spend(self._completed)))
        self._record_metric("risk_score", self.risk.score())
        # Opportunity detection: overload fires employee_overloaded.
        if self.workforce.projected_surplus(work_units) < 0:
            self.events.record(
                SimEvent(
                    tick=tick,
                    kind=Kinds.EMPLOYEE_OVERLOADED,
                    entity_ref="workforce",
                    severity="warning",
                    detail={"headcount": self.workforce.headcount},
                )
            )
        # KPI forecast trajectory (capped by limits in a _check_limits hook).
        kpi_forecast = self.kpi_sim.forecast("throughput", growth_rate=0.01, horizon_ticks=1)
        self._record_metric("kpi_throughput", kpi_forecast[-1])

    def _record_metric(self, key: str, value: float) -> None:
        self.metrics.setdefault(key, []).append(value)

    def summary(self) -> dict[str, Any]:
        def agg(values: list[float]) -> dict[str, float]:
            if not values:
                return {}
            return {
                "min": round(min(values), 4),
                "max": round(max(values), 4),
                "mean": round(statistics.fmean(values), 4),
                "median": round(statistics.median(values), 4),
                "p90": round(self._percentile(values, 90), 4),
            }

        return {k: agg(v) for k, v in self.metrics.items()}

    @staticmethod
    def _percentile(values: list[float], q: float) -> float:
        values = sorted(values)
        if not values:
            return 0.0
        k = (len(values) - 1) * q / 100.0
        f = int(k)
        c = min(f + 1, len(values) - 1)
        return values[f] + (values[c] - values[f]) * (k - f)


class SimulationEngine:
    """Persistence-facing engine: owns Simulation/SimulationRun/Iteration rows."""

    def __init__(
        self,
        db: Session,
        *,
        max_ticks: int = 500,
        max_events: int = 5000,
        run_timeout_seconds: float = 60.0,
        max_iterations: int = 50,
        gate: ConcurrentRunGate | None = None,
    ) -> None:
        self._db = db
        self.max_ticks = max_ticks
        self.max_events = max_events
        self.max_iterations = max_iterations
        self.run_timeout_seconds = run_timeout_seconds
        # Phase 12 resource governance: records sim_runs/iterations/events and
        # enforces configured budgets + the in-process concurrency ceiling.
        self._budget = Phase12RunBudget(db)
        self._gate = gate or ConcurrentRunGate()

    # ── Creation ──────────────────────────────────────────────────────

    def create(
        self,
        *,
        company_id: UUID | None,
        name: str,
        description: str | None = None,
        scenario_type: str = "custom",
        assumptions: dict[str, Any] | None = None,
        horizon_days: int | None = None,
        clock_tick: str | None = None,
        created_by: UUID | None = None,
    ) -> Simulation:
        sim = Simulation(
            company_id=company_id,
            name=name,
            description=description,
            scenario_type=scenario_type,
            assumptions_json=assumptions or None,
            horizon_days=horizon_days,
            clock_tick=clock_tick or "day",
            model_name="nexus-v1-default",
            model_version="1.0",
            status=SimStatus.DRAFT.value,
            sandboxed=True,
            created_by=created_by,
        )
        self._db.add(sim)
        self._db.commit()
        return sim

    def get(self, simulation_id: UUID) -> Simulation | None:
        return self._db.get(Simulation, simulation_id)

    def list_(self, company_id: UUID | None) -> list[Simulation]:
        stmt = select(Simulation).order_by(Simulation.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(Simulation.company_id == company_id)
        return list(self._db.execute(stmt).scalars().all())

    def ready(self, simulation_id: UUID) -> Simulation:
        sim = self.get(simulation_id)
        if sim is None:
            raise SimulationEngineError(f"Simulation {simulation_id} not found")
        if sim.status not in (SimStatus.DRAFT.value, SimStatus.READY.value):
            raise SimulationEngineError(
                f"Simulation {simulation_id} is {sim.status}; must be draft or ready to run"
            )
        sim.status = SimStatus.READY.value
        self._db.commit()
        return sim

    # ── Runs ──────────────────────────────────────────────────────────

    def run(
        self,
        *,
        simulation_id: UUID,
        scenario_id: UUID | None = None,
        seed: str | None = None,
        iterations: int | None = None,
        variables: list[SimulationVariable] | None = None,
        baseline_values: dict[str, float] | None = None,
    ) -> SimulationRun:
        sim = self.ready(simulation_id)

        # Scenarios validated by the engine (ScenarioEngine is called by the API).
        scenario = Scenario(
            name=sim.name,
            scenario_type=sim.scenario_type,
            simulation_id=simulation_id,
            company_id=sim.company_id,
            assumptions=sim.assumptions_json or {},
            horizon_days=sim.horizon_days,
            variables=list(variables or []),
            is_baseline=sim.baseline_simulation_id is None,
        )
        n_iterations = min(iterations or 1, self.max_iterations)
        run = self._new_run(sim, scenario_id, seed)
        try:
            # Governance (Phase 12): refuse when the day's sim-run budget is
            # exhausted or the in-process concurrency ceiling is reached. The
            # denied run is recorded as FAILED so the refusal is auditable.
            self._budget.checkrecord("sim_runs", 1.0, company_id=sim.company_id)
            self._gate.acquire(sim.company_id)
            try:
                self._execute(
                    run,
                    scenario,
                    n_iterations=n_iterations,
                    seed=seed,
                    baseline_values=baseline_values,
                )
            finally:
                self._gate.release(sim.company_id)
        except SimulationEngineError as exc:
            run.status = SimStatus.FAILED.value
            run.error_message = str(exc)
            self._db.commit()
            return run
        return run

    def _new_run(
        self, sim: Simulation, scenario_id: UUID | None, seed: str | None
    ) -> SimulationRun:
        run = SimulationRun(
            simulation_id=sim.id,
            scenario_id=scenario_id,
            company_id=sim.company_id,
            status=SimStatus.RUNNING.value,
            seed=seed,
            model_name="nexus-v1-default",
            model_version="1.0",
            started_at=_dt.datetime.now(),
        )
        self._db.add(run)
        self._db.commit()
        return run

    def _execute(
        self,
        run: SimulationRun,
        scenario: Scenario,
        *,
        n_iterations: int,
        seed: str | None,
        baseline_values: dict[str, float] | None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        aggregates: dict[str, list[float]] = {}
        for i in range(1, n_iterations + 1):
            iter_seed = seed if n_iterations == 1 else f"{seed or 'iter'}-{i}"
            result = self._execute_iteration(run, scenario, i, iter_seed, baseline_values)
            self._budget.checkrecord("sim_iterations", 1.0, company_id=run.company_id)
            self._persist_iteration(run, i, iter_seed, result)
            for k, v in result.get("metric_means", {}).items():
                aggregates.setdefault(k, []).append(v)
            if time.monotonic() - started > self.run_timeout_seconds:
                raise SimulationEngineError(
                    f"Run exceeded timeout of {self.run_timeout_seconds}s after {i} iterations"
                )
        run.status = SimStatus.COMPLETED.value
        run.completed_at = _dt.datetime.now()
        self._persist_summary(run, aggregates, n_iterations)
        self._db.commit()
        return {"iterations": n_iterations, "aggregates": aggregates}

    def _execute_iteration(
        self,
        run: SimulationRun,
        scenario: Scenario,
        iter_index: int,
        seed: str | None,
        baseline_values: dict[str, float] | None,
    ) -> dict[str, Any]:
        model = AgentBehaviorModel(seed=seed)
        sandbox = SimulationSandbox(
            scenario=scenario,
            model=model,
            company_id=run.company_id,
            baseline_values=baseline_values,
        )
        horizon = min(scenario.horizon_days or 30, self.max_ticks)
        run.tick_count = horizon
        # Pre-seed the sandbox clock with the whole horizon so due() fires live.
        sandbox.clock.schedule(
            Kinds.KPI_THRESHOLD,
            at_tick=2,
            recurring_every=7,
            payload={"threshold": 0.6},
        )
        for tick in range(1, horizon + 1):
            if sandbox.clock.paused:
                sandbox.clock.resume()
            sandbox.clock.tick_forward(1)
            sandbox.step(tick)
            if sandbox.events.count() > self.max_events:
                raise SimulationEngineError(
                    f"Simulation exceeded event budget of {self.max_events}"
                )
            if len(sandbox.entities) > 5000:
                raise SimulationEngineError("Simulation exceeded entity budget")
        # Governance: record the event volume for this iteration (the hard
        # ``max_events`` cap above already failed the run on runaway volume).
        self._budget.checkrecord(
            "sim_events", float(sandbox.events.count()), company_id=run.company_id
        )
        # Persist iteration metrics/events inside the sandbox bounds.
        self._persist_iteration_metrics(run, iter_index, sandbox)
        self._persist_selected_events(run, iter_index, sandbox, limit=100)
        return {
            "metric_means": {k: statistics.fmean(v) for k, v in sandbox.metrics.items()},
        }

    def _persist_iteration(
        self, run: SimulationRun, i: int, seed: str | None, result: dict[str, Any]
    ) -> None:
        row = SimulationIteration(
            run_id=run.id,
            company_id=run.company_id,
            iteration=i,
            seed=seed,
            status=SimStatus.COMPLETED.value,
            result_json=result,
        )
        self._db.add(row)
        self._db.commit()

    def _persist_iteration_metrics(
        self, run: SimulationRun, i: int, sandbox: SimulationSandbox
    ) -> None:
        for key, values in sandbox.metrics.items():
            self._db.add(
                SimulationMetric(
                    run_id=run.id,
                    company_id=run.company_id,
                    key=key,
                    value=statistics.fmean(values),
                    tick=i,
                )
            )
        self._db.commit()

    def _persist_selected_events(
        self, run: SimulationRun, i: int, sandbox: SimulationSandbox, *, limit: int
    ) -> None:
        for ev in sandbox.events.all(limit=limit):
            self._db.add(
                SimulationEvent(
                    run_id=run.id,
                    company_id=run.company_id,
                    tick=ev.tick,
                    event_kind=ev.kind,
                    entity_ref=ev.entity_ref,
                    detail_json=ev.detail,
                )
            )
        self._db.commit()

    def _persist_summary(
        self, run: SimulationRun, aggregates: dict[str, list[float]], n: int
    ) -> None:
        summary: dict[str, Any] = {"iterations": n, "metrics": {}}
        for key, values in aggregates.items():
            if not values:
                continue
            summary["metrics"][key] = {
                "min": round(min(values), 4),
                "max": round(max(values), 4),
                "mean": round(statistics.fmean(values), 4),
                "median": round(statistics.median(values), 4),
            }
            self._db.add(
                SimulationOutcome(
                    run_id=run.id,
                    company_id=run.company_id,
                    output_kind=SimulationOutputKind.SIMULATED.value,
                    metric_key=key,
                    value=statistics.fmean(values),
                )
            )
        run.summary_json = summary
        self._db.commit()

    # ── Lifecycle controls ────────────────────────────────────────────

    def cancel(self, run_id: UUID) -> SimulationRun:
        run = self.get_run(run_id)
        if run.status not in (
            SimStatus.READY.value,
            SimStatus.RUNNING.value,
            SimStatus.PAUSED.value,
        ):
            raise SimulationEngineError(f"Cannot cancel run {run.status}")
        run.status = SimStatus.CANCELLED.value
        self._db.commit()
        return run

    def pause(self, run_id: UUID) -> SimulationRun:
        run = self.get_run(run_id)
        if run.status != SimStatus.RUNNING.value:
            raise SimulationEngineError(f"Cannot pause run {run.status}")
        run.status = SimStatus.PAUSED.value
        self._db.commit()
        return run

    def get_run(self, run_id: UUID) -> SimulationRun:
        run = self._db.get(SimulationRun, run_id)
        if run is None:
            raise SimulationEngineError(f"Run {run_id} not found")
        return run

    def run_state(self, run_id: UUID) -> dict[str, Any]:
        run = self.get_run(run_id)
        events = list(
            self._db.execute(
                select(SimulationEvent)
                .where(SimulationEvent.run_id == run_id)
                .order_by(SimulationEvent.tick)
                .limit(100)
            ).scalars()
        )
        metrics = list(
            self._db.execute(
                select(SimulationMetric).where(SimulationMetric.run_id == run_id)
            ).scalars()
        )
        return {
            "run_id": str(run.id),
            "status": run.status,
            "tick": run.tick_count,
            "simulation_id": str(run.simulation_id),
            "scenario_id": str(run.scenario_id) if run.scenario_id else None,
            "events": [
                {
                    "tick": e.tick,
                    "kind": e.event_kind,
                    "entity_ref": e.entity_ref,
                    "detail": e.detail_json,
                }
                for e in events
            ],
            "metrics": [{"key": m.key, "value": m.value, "tick": m.tick} for m in metrics],
        }

    # ── Checkpoints ───────────────────────────────────────────────────

    def checkpoint(self, run_id: UUID, *, tag: str | None = None) -> SimulationCheckpoint:
        run = self.get_run(run_id)
        row = SimulationCheckpoint(
            run_id=run_id,
            company_id=run.company_id,
            action=SimCheckpointAction.CHECKPOINT.value,
            tick=run.tick_count,
            state_json={
                "status": run.status,
                "tag": tag,
                **({"summary": run.summary_json} if run.summary_json else {}),
            },
        )
        self._db.add(row)
        self._db.commit()
        return row

    def restore(self, run_id: UUID, checkpoint_id: UUID) -> SimulationRun:
        run = self.get_run(run_id)
        cp = self._db.get(SimulationCheckpoint, checkpoint_id)
        if cp is None or cp.run_id != run_id:
            raise SimulationEngineError(f"Checkpoint {checkpoint_id} not found for run {run_id}")
        cp.action = SimCheckpointAction.RESTORE.value
        cp.state_json = cp.state_json or {}
        run.status = SimStatus.READY.value
        self._db.commit()
        return run

    # ── Comparisons ───────────────────────────────────────────────────

    def compare(self, *, baseline_run_id: UUID, scenario_run_id: UUID) -> SimulationComparison:
        base = self.get_run(baseline_run_id)
        b_metrics = self.run_state(baseline_run_id).get("metrics", [])
        s_metrics = self.run_state(scenario_run_id).get("metrics", [])
        b = {m["key"]: m["value"] for m in b_metrics}
        s = {m["key"]: m["value"] for m in s_metrics}
        deltas: dict[str, Any] = {}
        for key in sorted(set(b) | set(s)):
            bv = b.get(key) or 0.0
            sv = s.get(key) or 0.0
            deltas[key] = {
                "baseline": bv,
                "scenario": sv,
                "delta": round(sv - bv, 4),
            }
        smallest = (
            min(deltas.items(), key=lambda kv: abs(kv[1]["delta"])) if deltas else (None, None)
        )
        comp = SimulationComparison(
            baseline_run_id=baseline_run_id,
            scenario_run_id=scenario_run_id,
            company_id=base.company_id,
            metric_deltas_json=deltas,
            bottleneck_json=(
                {"least_delta": smallest[0] if smallest else None} if smallest else None
            ),
            summary=None,
        )
        self._db.add(comp)
        self._db.commit()
        return comp
