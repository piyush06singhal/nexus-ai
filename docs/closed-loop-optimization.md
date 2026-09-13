# NEXUS — Closed-Loop Optimization

What the Phase 12 closed-loop orchestration actually delivers, how to run it, and
what it honestly does not claim. Part of the Phase 12 suite — see
[phase-12.md](phase-12.md) for the umbrella, and the sibling docs
[simulation.md](simulation.md), [optimization.md](optimization.md),
[experimentation.md](experimentation.md), [benchmarking.md](benchmarking.md), and
[agent-marketplace.md](agent-marketplace.md).

---

## 1. High-level

The closed loop (`app/phase12/loop.py`) unifies the Phase 12 stack into the
§58 orchestration:

```text
OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE → EXECUTE → MEASURE → LEARN → RE-SIMULATE
```

`NEXUSOptimizationLoop` drives and tracks that cycle as an
`autonomous_optimization_cycles` record whose status enum is the authoritative state
machine: `observing → simulating → optimizing → proposing → awaiting_approval →
executing → measuring → learning → completed`, with `blocked / failed / cancelled`
as terminal states. The loop **reuses existing governance and measurement** — Phase 9
`ApprovalGateManager` for the gate, Phase 9 `LessonRecorder` for lessons, Phase 8
`KPIService` for observation. It **never modifies production systems itself**: after
approval, execution only records a reference (`execute_ref`) to the delegated
action; the cycle measures and learns honestly, and re-simulation is the operator's
follow-on.

## 2. What landed

- **`NEXUSOptimizationLoop`** (`loop.py`) — `create_cycle` / `get_cycle` /
  `list_cycles` + one stage method per state: `observe` / `simulate` / `optimize` /
  `propose` / `require_approval` / `execute` / `measure` / `learn` / `complete` /
  `cancel`, plus a `run_full_cycle` convenience
  (create → observe → simulate → optimize → propose → require_approval).
- **Stage semantics** —
  - `observe()` (read-only) — best-effort Phase 8 KPI observation through
    `KPIService`; stored in `observed_json` with `source: "phase-8-kpis"` and
    `readonly: True`. A failure makes observation best-effort with an `error` note —
    it never blocks the cycle.
  - `simulate()` — links the chosen `scenario_ids` to the cycle
    (`scenario_ids_json`); the `SimulationEngine` executes them.
  - `optimize()` / `propose()` — advance the state machine toward the
    recommendation from an optimization run.
  - `require_approval()` — opens an `ApprovalGateManager`
    `major_strategic_change_approval` gate with requested action
    `closed_loop.optimization.apply` (module `phase12`, risk `medium`), persists the
    `approval_gate_id`, and moves to `awaiting_approval`.
  - `execute()` — **only proceeds when the gate is approved** (`gate.status ==
    "approved"`; otherwise `LoopError`). It records `execute_ref` — a reference to
    the delegated action — and does not itself perform production side effects.
  - `learn()` — records a `strategic_insight` lesson via `LessonRecorder` (Phase 9
    reuse) whose content explicitly says *simulated forecast vs measured outcomes
    should be compared before re-simulation*; the source JSON carries the cycle,
    simulation run, optimization run, and recommendation ids.
- **API** (`app/phase12/api/cycle.py`) — mounted at `/api/v1/optimization-cycles`
  (see §4).
- **Migration** — `0014_phase12_sim_opt_mkt` adds `autonomous_optimization_cycles`
  (observed_json, scenario_ids_json, simulation/optimization run ids,
  recommendation_id, approval_gate_id, execute_ref, measures_json, lesson_json,
  error_message) additively.
- **Demo** — the Phase 12 seed's Part 6 runs a full cycle and proves that
  `execute()` without an approved gate is **blocked**, then approves the gate and
  drives it to `completed`; the §69 full E2E does the same against a live company,
  asserting every `simulation_outcomes` row is labeled SIMULATED/FORECAST, never
  ACTUAL.

## 3. Governance

- **The gate decides** — execution is hard-blocked until the
  `ApprovalGateManager` gate is `approved`; one gate authorizes exactly one action,
  once (that is the Phase 9 invariant this composes). The `/approve` API route is
  the only path through to `execute()`.
- **No simulated side effects** — the loop records references and observations; the
  sandboxed simulators underneath refuse any would-be production/external action.
- **Honest lesson** — the recorded lesson instructs comparison of forecast vs
  measured before re-simulation, keeping the loop honest about its own modeled
  outputs.

## 4. API map (`/api/v1/optimization-cycles`)

```text
GET    /optimization-cycles              list cycles (?company_id, newest first)
POST   /optimization-cycles              create a cycle (observe=true runs observation)
GET    /optimization-cycles/{id}         get one cycle
POST   /optimization-cycles/{id}/run     simulate → optimize → propose → require_approval
POST   /optimization-cycles/{id}/approve approve the gate, then execute()
POST   /optimization-cycles/{id}/cancel  cancel (records operator cancellation)
```

## 5. How to verify

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_phase12_closed_loop.py -q

# Migration round-trip (revision 0014_phase12_sim_opt_mkt)
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade 0013 && .venv/bin/alembic upgrade head

# Live smoke (server on 127.0.0.1:8000)
.venv/bin/python -m scripts.smoke_api --phase 12
```

The Phase 12 demo runs both Part 6 (bounded closed-loop) and §69 (full
autonomous-company-optimization E2E — observe KPIs → simulate → optimize → propose →
approve → execute → measure → learn → complete, outcomes labeled SIMULATED):

```bash
cd apps/api
.venv/bin/python -m scripts.seed_simulation_optimization [--reset]
```

## 6. Known honest limits

- **This is an orchestration and tracking loop, not an auto-pilot.** The cycle
  records references and delegates; the actual production change (if any) is the
  governed action's job, gated by a human approval. Nothing in Phase 12 automatically
  replaces production configuration or emits real side effects from within a
  simulation.
- **Observation is read-only KPI snapshots** — the loop observes; it does not
  run inference or learning over live telemetry on its own. Re-simulation after
  learn is the operator's follow-on, not an automatic state-machine transition.
- **No self-modification, no RL** (§48/§49/§66) — there is no self-modification
  loop, no reinforcement learning, no reward-driven self-modification of the codebase
  or of governance, and no simulation-triggered real side effect anywhere in Phase
  12. The closure here is *propose → approve → execute → measure → learn → compare
  before re-simulating*, always human-gated.
- Lessons are recorded as `strategic_insight` with an explicit
  compare-forecast-against-measured instruction — the point is supervision, not
  autonomous retraining.