# NEXUS — Phase 12 Simulation, Optimization & Agent Marketplace (What Changed)

What Phase 12 actually delivered, how to run it, and how to verify it. Companion to
the six topic docs: [simulation.md](simulation.md), [optimization.md](optimization.md),
[experimentation.md](experimentation.md), [benchmarking.md](benchmarking.md),
[agent-marketplace.md](agent-marketplace.md), and
[closed-loop-optimization.md](closed-loop-optimization.md). Style follows
[phase-11-production-hardening.md](phase-11-production-hardening.md).

---

## 1. High-level

Phase 12 makes NEXUS **able to reason forward about its own operation before
deciding**: model an organization in a closed sandbox (simulation), search
governed allocation/strategy choices (optimization), run approval-gated what-if
analyses with honest conclusions (experimentation), score agents/versions on
deterministic suites (benchmarking), catalog and recommend agent packages
(agent marketplace), and close the loop
`OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE → EXECUTE → MEASURE → LEARN →
RE-SIMULATE` (closed-loop). It is a **modeled, governed layer that composes
Phases 0–11** — it reuses `ResourceGovernanceService` (11), `PolicyEngine` (11),
`ApprovalGateManager` (9/11), `LessonRecorder` (9), `KPIService` (8), the Phase 6
evaluation metrics, and Phase 7/8 company data — and it **does not build a second**
runtime, memory, company, execution, or governance system.

### Design decisions locked

1. **Simulation is a closed sandbox.** Simulated outputs are stored as labeled
   `SIMULATED`/`FORECAST` rows and are **modeled estimates, never ACTUAL, never a
   guaranteed prediction**. KPI simulation never writes real `kpi_values` rows, and
   a run that attempts a real side effect is refused (`SANDBOX_REFUSAL`) and FAILED.
2. **Optimization proposes; governance decides.** Every recommendation carries the
   §46 ten-question explainability block; candidates failing Phase 11 policy or
   resource limits are rejected before scoring; applying anything requires an
   `ApprovalGateManager` gate. No auto-production-replacement.
3. **The marketplace is internal/private and metadata-only.** Packages carry
   capabilities/skills/requirements/benchmark scores/security classification — never
   credentials, secrets, private memories, execution history, tokens, or executable
   payloads (`PackageScanner` rejects them at every entry point). Safe install
   (§37) is approval-gated.
4. **No self-modification, no RL** (§48/§49/§66). No simulation-triggered real side
   effects; the closed loop records references and delegates production change to
   governed, human-approved actions.
5. **Deterministic defaults, optional seeded randomness.** The default behavior
   model, benchmarks, and optimizers are deterministic and provider-neutral (no
   external SaaS, no paid model calls); supplying a seed opts into reproducible
   Monte-Carlo variance.

## 2. What landed, wave by wave

**Wave 1 — Simulation.** `app/phase12/engine.py` (`SimulationEngine`,
`SimulationSandbox`, lifecycle `DRAFT → READY → RUNNING ⇄ PAUSED → COMPLETED /
FAILED / CANCELLED`, multi-run with per-iteration seeds + aggregated
min/max/mean/median/p90, checkpoints/restore, comparisons with metric deltas +
bottleneck), `simulators.py` (`WorkforceSimulator`, `BudgetSimulator` with an
optional Phase 11 resource check, `KpiSimulator` — reads definitions, never writes
`kpi_values`, `RiskSimulator` with 8 dimensions + modeled stress), `scenario.py`
(`ScenarioEngine`, 11 scenario types, rejects invalid sims before any run),
`variables.py` (9 typed, bounded kinds), `events.py` (15 event kinds incl.
`sandbox_refusal`), `behavior.py` (`AgentBehaviorModel`), `sim_clock.py`
(day/hour/week clock with pause/seek/recurring scheduling), `digital_twin.py`
(`CompanyDigitalTwin` — versioned, read-only, pure-SELECT snapshots with a
"not a prediction" disclaimer).

**Wave 2 — Optimization.** `optimization.py` (`OptimizationEngine`, strategies
`greedy`/`exhaustive`/`ranking`, `Objective`/`Variable`/`Constraint` vocabulary,
governance-checked candidates, §46 explainability block, `recommend` →
`approve_rec`/`reject_rec`), models `optimization_problems/variables/constraints/
objectives/runs/candidates/scores/recommendations/lessons`.

**Wave 3 — Experimentation.** `experiments.py` (`ExperimentEngine` lifecycle
`DRAFT → PENDING_APPROVAL → APPROVED → RUNNING → COMPLETED | STOPPED | CANCELLED`,
baseline + variants, `record_metric`, `complete_experiment` with WINNER/LOSER/
INCONCLUSIVE + confidence + limitations, default `inconclusive`), models
`experiments/variants/runs/metrics/results`.

**Wave 4 — Benchmarking.** `benchmarking.py` (`BenchmarkEngine`, `BenchmarkSuite`/
`BenchmarkCase`, deterministic seeded scoring, 8 dimensions, per-case results +
per-dimension `AgentBenchmarkScore` aggregates, versioned for agent comparison,
reuses Phase 6 evaluation metrics), models `benchmarks/suites/cases/runs/results/
agent_benchmark_scores`.

**Wave 5 — Agent marketplace.** `marketplace.py` (`MarketplaceService`,
`PackageScanner`, metadata-only packages, semver versions, publish/deprecate,
approval-gated safe install, reviews rating 1..5, attached benchmark scores),
`recommend.py` (`AgentRecommendationEngine` — measured signals only, ranked ≤10,
reasoning + tradeoffs, defaults to `pending_approval`), reputation from measurable
sources only; models `agent_packages/versions/capabilities/dependencies/benchmarks/
reviews/installations/recommendations/reputation_records`.

**Wave 6 — Closed loop.** `loop.py` (`NEXUSOptimizationLoop`, cycle state machine
`observing → … → learning → completed` with `blocked/failed/cancelled` terminal,
approval-gated execute that records a reference only, `learn()` via Phase 9
`LessonRecorder`, `run_full_cycle` convenience), model
`autonomous_optimization_cycles`.

**Wave 7 — API, schema, governance, seed, checks.** One mount
`app/phase12/api/router.py` keeps `app/api/v1/router.py` a one-liner; routers for
simulations, optimization, experiments, benchmarks, marketplace, agent-recommendations,
and optimization-cycles + schemas in `app/schemas/phase12.py`; migration
`0014_phase12_sim_opt_mkt` (43 additive tables); governance in `governance.py`
(8 Phase 12 budget categories + `ConcurrentRunGate` ceiling 8) and two new
`production_readiness` checks; `scripts/seed_simulation_optimization.py` (Parts 1–6
+ §69 E2E, deterministic and self-asserting).

**Wave 8 — Frontend.** Four UI centers — `apps/web/src/app/simulations/`
(list/detail, scenarios, compare), `optimization/` (problems, recommendations),
`experiments/`, and `marketplace/` (catalog, agent detail, recommendations) — on a
shared `Phase12Shell`, with confirmation dialogs on every destructive/approving
action and **honest labeling: SIMULATED / FORECAST / ACTUAL and RECOMMENDED /
APPROVED / EXECUTED** throughout. See the web routes in
`apps/web/src/app/{simulations,optimization,experiments,marketplace}/`.

## 3. Configuration (`.env` / settings)

**Phase 12 adds no new environment variables or settings.** Searching
`app/core/config.py` confirms no `sim_*`/`phase12*` settings exist. Phase 12
composes Phase 11's governance knobs:

```bash
# Phase 12 is configuration-free beyond the Phase 11 governance/limit vars.
# Resource budgets per category (sim_runs, sim_iterations, sim_events,
# optimization_candidates, benchmark_runs, benchmark_cases, experiment_runs,
# marketplace_ops) are DB-configured via the Phase 11 governance API —
# see /governance/resources and /governance/limits below.
#
# Engine hard ceilings are constructor defaults (not env):
#   max_ticks=500, max_events=5000, max_iterations=50, run_timeout_seconds=60
# Concurrency ceiling: MAX_CONCURRENT_PHASE12_RUNS = 8 (editable constant).
```

Relevant Phase 11 settings that govern Phase 12 run behavior:
`APPROVAL_REQUIRE_SEPARATION_OF_DUTIES`, `APPROVAL_SELF_APPROVAL_BLOCKED`,
`RESOURCE_MAX_*` defaults, and `AUTH_ENABLED` (auth stays open in dev/test so the
full Phase 0–11 suite stays green; each Phase 12 security test flips it on and
proves cross-company isolation).

## 4. Data model

Migration `0014_phase12_sim_opt_mkt` (revision `0014_phase12_sim_opt_mkt`, revises
`0013_security_governance`) is a **pure additive** revision of **43 tables** created
from `app/db/models/phase12.py` metadata so DDL can never drift from the models.
Nothing existing is altered; `company_id` FK + index on every tenant-scoped table.
All enums follow the project `StrEnum` / `native_enum=False` VARCHAR convention, and
`_types.py` asserts service enums mirror the model enums at import (drift protection).

## 5. Running the verifications

From `apps/api` (venv `apps/api/.venv`):

```bash
# Unit verification — the full Phase 12 suite (7 files, 112 tests)
.venv/bin/python -m pytest tests/test_phase12_simulation.py tests/test_phase12_optimization.py \
  tests/test_phase12_experiments.py tests/test_phase12_marketplace.py \
  tests/test_phase12_closed_loop.py tests/test_phase12_security.py tests/test_phase12_perf.py -q

# Full backend regression
.venv/bin/python -m pytest -q

# Lint + format
.venv/bin/ruff check app tests scripts && .venv/bin/ruff format --check app tests scripts

# Migration round-trip (revision 0014_phase12_sim_opt_mkt)
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade 0013 && .venv/bin/alembic upgrade head

# Web (from apps/web)
npx tsc --noEmit && npm run lint && npm run build && npm run test -- --run

# Live smoke — server on 127.0.0.1:8000 in another terminal
# --phase 12 targets /simulations /optimization /experiments /benchmarks
# /marketplace /agent-recommendations /optimization-cycles (+ shared core routes)
.venv/bin/python -m scripts.smoke_api --phase 12
.venv/bin/python -m scripts.smoke_api --phase 11

# Deterministic demo (SQLite or Postgres; --reset rebuilds the demo company)
DATABASE_URL="sqlite:////tmp/nexus_p12_demo.db" \
  .venv/bin/python -m scripts.seed_simulation_optimization [--reset]
#   part 1: what-if grow engineering 5→7 (SIMULATED)
#   part 2: agent optimization on a shared benchmark (v1.0 vs v1.1)
#   part 3: resource-allocation optimization + §46 explainable recommendation
#   part 4: product launch 4wk vs 6wk comparison (deltas + bottleneck)
#   part 5: research-analyst-pro published → benchmarked → recommended → safe install
#   part 6: closed-loop cycle (approval-gated; execute blocked pre-approval)
#   part 69: full NEXUS autonomous-company-optimization E2E (outcomes SIMULATED)

# Production readiness — dev passes 8 / warns 8 / fails 0
.venv/bin/python -m app.checks.production_readiness
```

## 6. Known honest limits (documented, not claimed)

- **Simulation outputs are SIMULATED / FORECAST / modeled estimates — never ACTUAL,
  never guaranteed predictions.** KPI simulation reads real definitions but never
  overwrites real `KpiValue` rows; sandboxed sims refuse any production/external
  side effect and fail the run (`sandbox_refusal`).
- **Optimization proposes; governance decides.** Every recommendation carries the
  §46 explainability block; applying one requires approval via `ApprovalGateManager`;
  there is no auto-production-replacement and no optimization-run side effect on
  production rows.
- **The marketplace is internal/private metadata-only.** Capabilities, skills,
  requirements, benchmark scores, security classification — never credentials,
  secrets, private memories, execution history, tokens, or executable payloads;
  `PackageScanner` rejects them at create/version/install and the scan is public via
  `POST /marketplace/scan`.
- **No self-modification, no RL** (§48/§49/§66): the closed loop is
  propose → approve → execute(reference) → measure → learn → *compare before
  re-simulating* — always human-gated, never a reward-driven self-modifying system.
- **Deterministic default models** — the default behavior model and benchmark
  scores are converged/fixed (seeded randomness is optional); model *versioning*
  (`nexus-v1-default` / `1.0`) is recorded on every sim/run for review, not a fleet
  of calibrated models.
- **Honest experiment conclusions** — WINNER / LOSER / INCONCLUSIVE with explicit
  sample size, confidence, and limitations; the engine defaults to `inconclusive`
  and stores your declarations — it does not compute or overstate significance.
- **Reputation from measurable signals only** — benchmark/success/verification/
  recovery/consistency/rating, never self-rating; recommendation falls back to
  conservative base constants when no measured signal exists yet.
- **Governance budgets are DB-configured** — Phase 12 categories
  (`sim_runs`, `sim_iterations`, `sim_events`, `optimization_candidates`,
  `benchmark_runs`, `benchmark_cases`, `experiment_runs`, `marketplace_ops`)
  behave as unlimited until an operator sets per-company limits via the Phase 11
  governance API; the engine's own hard ceilings (ticks/events/iterations/timeout/
  candidates) and the concurrency gate are always active regardless.
- **Deployment items carry forward from Phase 11** — no OS-level process
  sandboxing for computation, no Redis-backed worker pools, no managed secrets
  vault, no TLS termination inside the API, no compliance certifications claimed.
- The one pre-existing full-suite ordering flake (`test_full_orchestrator_pipeline`)
  passes in isolation and is not a Phase 12 regression.

---

## Cross-links

- [simulation.md](simulation.md) — engine, sandbox, simulators, scenarios, clock,
  digital twin, run lifecycle, API, budgets.
- [optimization.md](optimization.md) — problem/run/strategy, governed evaluation,
  §46 recommendations, approval flow, API.
- [experimentation.md](experimentation.md) — approval-gated lifecycle, honest
  conclusions Win/Lose/Inconclusive, API.
- [benchmarking.md](benchmarking.md) — suites/cases, 8 dimensions, deterministic
  scoring, versioned agent scores, API.
- [agent-marketplace.md](agent-marketplace.md) — metadata-only packages,
  `PackageScanner`, safe install, recommendations, reputation, API.
- [closed-loop-optimization.md](closed-loop-optimization.md) — the §58 loop, cycle
  state machine, approval-gated execute, lesson recording, API.