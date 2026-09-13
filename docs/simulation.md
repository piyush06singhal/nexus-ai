# NEXUS — Simulation Engine

What the Phase 12 simulation engine actually delivers, how to run it, and what it
honestly does not claim. Part of the Phase 12 suite — see
[phase-12.md](phase-12.md) for the umbrella, and the sibling docs
[optimization.md](optimization.md), [experimentation.md](experimentation.md),
[benchmarking.md](benchmarking.md), [agent-marketplace.md](agent-marketplace.md),
and [closed-loop-optimization.md](closed-loop-optimization.md).

---

## 1. High-level

The simulation engine (`app/phase12/engine.py`) models an organization forward,
*tick by tick*, inside a **closed sandbox**. It never touches production data:
no HTTP, no email, no browser, no financial transaction, no real DB mutation.
All outputs are persisted as **SIMULATED / FORECAST** rows (`SimulationOutputKind`
labels the `simulation_outcomes` rows), never `ACTUAL` — KPI simulation reads real
KPI *definitions* (Phase 8) but never writes a real `kpi_values` row.

A simulation is a definition (`simulations` row) your run against a named
`SimulationScenario`. A run may hold N iterations (Monte-Carlo-style) with a
per-iteration seed, and the run summary aggregates each metric across iterations
(min / max / mean / median / p90). Runs are lifecycle-managed
(`DRAFT → READY → RUNNING → (PAUSED ⇄ RUNNING) → COMPLETED / FAILED / CANCELLED`),
bounded by hard engine ceilings (ticks, events, entities, timeout), charged against
Phase 11 resource budgets, and subject to an in-process concurrency ceiling.

## 2. What landed

- **`SimulationEngine`** (`engine.py`) — create/get/list/ready/run; checkpoint /
  restore (`SimulationCheckpoint`); pause / cancel on a run; `compare()` producing a
  `SimulationComparison` of baseline vs scenario metric **deltas** plus a
  `bottleneck_json` (smallest-delta metric). A run is isolated per company via
  `company_id` (FK + index) on every table.
- **`SimulationSandbox`** — the in-memory, closed execution context. It materialises
  a clock, event log, and the four simulators, then steps them tick by tick. If a
  modeled behavior attempts a production/external side effect, the sandbox
  **refuses** it: a `SANDBOX_REFUSAL` sim event is recorded (inside the sim only)
  and `SimulationSandboxRefusalError` fails the run with an honest message.
- **Simulators** (`simulators.py`) —
  - `WorkforceSimulator` — capacity, utilization, projected surplus (overload /
    idle signal), hiring-needed, availability.
  - `BudgetSimulator` — projected spend, remaining, utilization, cost/task,
    cost/success, cost variance. It *respects Phase 11 resource limits* via an
    injected `resource_check(category, amount)` callable (the sim layer stays
    decoupled from `ResourceGovernanceService`).
  - `KpiSimulator` — forecasts a KPI forward from its definition + a modeled
    trajectory; output kind is always `forecast`. **Never writes `kpi_values`.**
  - `RiskSimulator` — 8 dimension scores (operational / capacity / execution /
    dependency / budget / reliability / security / project) plus modeled `stress()`
    scenarios — no real system is ever attacked or stressed.
- **`SimulationClock`** (`sim_clock.py`) — deterministic accelerated time
  (resolutions `day` / `hour` / `week`), thread-safe tick/pause/resume/seek, and a
  scheduled event queue (one-shot or recurring) so runs are reproducible from a seed.
- **`AgentBehaviorModel`** (`behavior.py`) — how simulated agents behave. **Deterministic
  by default** (no randomness); supplying a `seed` opts into seeded stochasticity for
  Monte-Carlo-style multi-runs. Every run records `model_name` + `model_version`
  (`nexus-v1-default`/`1.0`) for reproducibility review.
- **`ScenarioEngine`** (`scenario.py`) — validates and normalises the **11 scenario
  types** (`baseline`, `what_if`, `stress_test`, `capacity_test`, `resource_test`,
  `strategy_test`, `workforce_test`, `agent_test`, `product_test`, `risk_test`,
  `custom`); rejects unsupported types, empty names, out-of-range horizons
  (1..3650 days), and invalid variables *at creation* — before any run.
- **`SimulationVariable`** (`variables.py`) — typed, bounded variables
  (integer / float / boolean / string / enum / duration / percentage / currency /
  rate) with min/max bounds and enum options validated at the boundary.
- **`CompanyDigitalTwin`** (`digital_twin.py`) — builds a **versioned, read-only**
  snapshot of a real company (Phase 8 company/departments/memberships/employees/
  backing agents/goals/KPIs) into a `simulation_snapshots` row. All readers are pure
  SELECTs; the source company is never mutated. Every snapshot carries a disclaimer
  that it is a *modeled* twin, not a prediction.
- **API** (`app/phase12/api/simulation.py`) — mounted at `/api/v1/simulations` (see
  §4 for the route map).
- **Migration** — `0014_phase12_sim_opt_mkt` (revision
  `0014_phase12_sim_opt_mkt`, revises `0013_security_governance`) adds the 13
  simulation tables additively — nothing existing is altered.

## 3. Resource governance

Phase 12 wraps the Phase 11 `ResourceGovernanceService` with its own category set
(`app/phase12/governance.py`):

- **Per-day budgets** — `sim_runs`, `sim_iterations`, `sim_events` (plus
  `optimization_candidates`, `benchmark_cases`, `benchmark_runs`,
  `experiment_runs`, `marketplace_ops` company-wide). When no per-company limit is
  configured, a category is *unlimited by governance* — but the engine's own hard
  ceilings still bound every run:
  - `max_ticks=500`, `max_events=5000` per run, `max_iterations=50`,
    `run_timeout_seconds=60.0` (all constructor defaults of `SimulationEngine`),
    plus a 5000-entity in-sandbox cap.
- **Concurrency ceiling** — `ConcurrentRunGate` enforces
  `MAX_CONCURRENT_PHASE12_RUNS = 8` simultaneous Phase 12 run executions per
  company (0 = unlimited; tighten the constant for shipping).
- **Tenant isolation** — every simulation table carries `company_id`
  (`simulations`, `simulation_scenarios`, `simulation_variables`,
  `simulation_runs`, `simulation_iterations`, `simulation_snapshots`,
  `simulation_outcomes`, `simulation_metrics`, `simulation_events`,
  `simulation_comparisons`, `simulation_checkpoints`, `simulation_entities`).

## 4. API map (`/api/v1/simulations`)

```text
GET    /simulations                                  list simulations (optional ?company_id)
POST   /simulations                                  create a simulation definition
POST   /simulations/{id}/run                         run it (seed / iterations / scenario_id)
GET    /simulations/{id}                             get one simulation
PUT    /simulations/{id}                             update name/assumptions/horizon/clock
GET    /simulations/scenarios                        list scenarios (?simulation_id)
POST   /simulations/scenarios                        create a scenario (validated pre-persist)
GET    /simulations/scenarios/{id}                   get one scenario
POST   /simulations/scenarios/{id}/run               run a specific scenario
GET    /simulations/runs/{run_id}                    get a run
GET    /simulations/runs/{run_id}/state              tick, events, metrics of a run
GET    /simulations/runs/{run_id}/events             sim event log (up to 500, by tick)
GET    /simulations/runs/{run_id}/metrics            per-tick metric rows
GET    /simulations/runs/{run_id}/results            summary + per-metric min/max/mean + outcomes
POST   /simulations/runs/{run_id}/pause              pause a running run
POST   /simulations/runs/{run_id}/cancel             cancel a run
POST   /simulations/compare/runs                     baseline vs scenario comparison (deltas)
GET    /simulations/twin                             list digital-twin snapshots
POST   /simulations/twin                             build a snapshot for a company_id
```

Static single-segment routes (`/scenarios`, `/twin`) are registered *before* the
`/{simulation_id}` param route so FastAPI resolves them literally.

## 5. How to verify

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_phase12_simulation.py tests/test_phase12_perf.py -q

# Migration round-trip (revision 0014_phase12_sim_opt_mkt)
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade 0013 && .venv/bin/alembic upgrade head

# Live smoke (server on 127.0.0.1:8000)
.venv/bin/python -m scripts.smoke_api --phase 12
```

The Phase 12 demo seeds a 5→7 headcount what-if, a product-launch 4wk-vs-6wk
comparison, and the §69 full E2E — every outcome asserted SIMULATED:

```bash
cd apps/api
.venv/bin/python -m scripts.seed_simulation_optimization [--reset]
```

## 6. Known honest limits

- **Outputs are modeled estimates** — SIMULATED / FORECAST, never ACTUAL, never a
  guaranteed prediction. Simulated KPI trajectories never write real
  `kpi_values` rows, and `simulation_outcomes` are labeled with
  `SimulationOutputKind`.
- **Default models are deterministic** — the default `AgentBehaviorModel` is
  seeding-free and converged on fixed parameters. Randomness (and therefore
  Monte-Carlo spread) only appears when you supply a seed. Model *versioning*
  is recorded on every sim/run (`nexus-v1-default` / `1.0`) rather than being a
  pluggable fleet of calibrated models.
- The simulators are simple projection functions over modeled assumptions — a
  capacity/utilization/spend/risk projection, not a calibrated physics of an
  organization. Inputs are modeled assumptions the author sets; they are not
  measurements.
- Stress scenarios and risk scores are internal modeled projections — no real
  system is ever stressed or attacked.
- Phase 12's governance budgets are *DB-configured* via the Phase 11 governance
  API; nothing enforces per-company Phase 12 budgets until an operator sets them.
  The engine's hard ceilings (ticks/events/iterations/timeout/entities) are always
  active regardless.
- Sandboxed sims cannot trigger real side effects: any would-be external/production
  action inside a run is refused and fails the run — this is a guarantee, and also
  a limit (simulations cannot directly validate against live systems).