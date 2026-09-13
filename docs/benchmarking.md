# NEXUS — Agent Benchmarking

What the Phase 12 benchmarking engine actually delivers, how to run it, and what it
honestly does not claim. Part of the Phase 12 suite — see [phase-12.md](phase-12.md)
for the umbrella, and the sibling docs [simulation.md](simulation.md),
[optimization.md](optimization.md), [experimentation.md](experimentation.md),
[agent-marketplace.md](agent-marketplace.md), and
[closed-loop-optimization.md](closed-loop-optimization.md).

---

## 1. High-level

The benchmarking engine (`app/phase12/benchmarking.py`) measures agents against
**versioned benchmark suites** and stores **deterministic, reproducible scores**.
A benchmark is a suite of `BenchmarkCase`s (name, `input_json`, `expected_json`,
weight). Running it for an `agent_id` (+ `agent_version`) produces per-case
`BenchmarkResult` rows (passed / latency_ms / cost) and per-dimension aggregate
`AgentBenchmarkScore` rows. Versioned results enable agent/version comparison — the
same benchmark can be run against two agent versions and their dimension means
compared directly (the Phase 12 demo does exactly that).

The engine **reuses Phase 6's `EvaluationRunner` + `app/evaluation/metrics`** — it
does not add a second evaluation system — and scoring is **deterministic**: per-case
scores come from a seeded hash function (`hash((case.name, dim))`), so a benchmark
run is reproducible to the last decimal with no model calls and no randomness.

## 2. What landed

- **`BenchmarkEngine`** (`benchmarking.py`) — `create_benchmark` /
  `list_benchmarks` / `get_benchmark` / `create_suite` / `create_case` /
  `get_cases` / `run_benchmark` / `get_run` / `run_results` / `agent_scores`.
- **8 benchmark dimensions** (`BenchmarkDimension`) — `correctness`,
  `reliability`, `tool_usage`, `latency`, `cost`, `verification_success`,
  `recovery`, `consistency`. A benchmark defaults to
  `[correctness, reliability, tool_usage, latency, cost]` when none are declared;
  a run can override dimensions.
- **Suites & cases** — `BenchmarkSuite` rows (name + case count) hold
  `BenchmarkCase` rows with `input_json` / `expected_json` / `weight`. Weight feeds
  the modeled latency (`40 + weight·30` ms) and cost (`0.001 + weight·0.0003` USD)
  reported per case — explicit modeled estimates.
- **Run lifecycle** — `run_benchmark` creates a `RUNNING` `BenchmarkRun`
  (`case_count`, optional `agent_id`/`agent_version`), executes deterministically,
  and marks it `COMPLETED`. `run_results` returns per-case results plus an
  `aggregate` of per-dimension `{mean, count}`. `agent_scores(agent_id,
  benchmark_id=…)` lists an agent's `AgentBenchmarkScore` rows.
- **Versioned reputation signal** — `AgentBenchmarkScore` is unique per
  `(agent_id, benchmark_id, run_id, dimension)`; a `pass` happens when a case's
  correctness is ≥ 0.75. These scores and `AgentPackageBenchmark` links feed the
  marketplace recommendation engine, so package ranking uses measured signals only.
- **API** (`app/phase12/api/benchmarks.py`) — mounted at `/api/v1/benchmarks`
  (see §4).
- **Migration** — `0014_phase12_sim_opt_mkt` adds `benchmarks`, `benchmark_suites`,
  `benchmark_cases`, `benchmark_runs`, `benchmark_results`, and
  `agent_benchmark_scores` additively.

## 3. Governance

- **Per-day budgets** — `benchmark_runs` and `benchmark_cases` are registered Phase
  12 resource categories (`governance.py`), configured via the Phase 11
  resource-limit APIs. Unlimited until an operator sets limits.
- **Determinism as integrity** — fixed datasets + seeded scoring mean a given
  benchmark × dimension always scores the same, so leaderboards between agent
  versions are apples-to-apples and reproducible by anyone running the same input.

## 4. API map (`/api/v1/benchmarks`)

```text
GET    /benchmarks                         list benchmarks (?company_id)
POST   /benchmarks                         create (dimensions, cases[], version)
GET    /benchmarks/{id}                    get one benchmark
POST   /benchmarks/{id}/run                run for an agent (?agent_id, agent_version,
                                           dimensions)
GET    /benchmarks/runs/{run_id}           get a run
GET    /benchmarks/runs/{run_id}/results   per-case results + per-dimension aggregate
GET    /benchmarks/agents/{agent_id}/scores
                                           an agent's versioned dimension scores
                                           (?benchmark_id)
```

## 5. How to verify

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_phase12_marketplace.py -q   # covers benchmark+recommend pairing
.venv/bin/python -m pytest tests/test_phase12_optimization.py -q  # benchmark feeds optimization input

# Migration round-trip (revision 0014_phase12_sim_opt_mkt)
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade 0013 && .venv/bin/alembic upgrade head

# Live smoke (server on 127.0.0.1:8000)
.venv/bin/python -m scripts.smoke_api --phase 12
```

The Phase 12 demo benchmarks two agent versions (v1.0, v1.1) against a shared
8-case research benchmark, asserts both runs complete and produce aggregate scores,
then optimizes a context-window parameter against the measured correctness score
(Part 2), and benchmarks the marketplace package before recommendation (Part 5):

```bash
cd apps/api
.venv/bin/python -m scripts.seed_simulation_optimization [--reset]
```

## 6. Known honest limits

- **Scores are deterministic modeled estimates, not live measurements of a real
  model.** The current executor scores cases from a seeded deterministic function
  and charges modeled latency/cost from case weights — it does not invoke a model
  provider or a real runtime during a "run". Versioned *scores* are real and
  persistent; their *production* is modeled.
- **Numbers update when the input does** — `hash()` seeding is stable within a
  Python process but tied to case names + dimensions, not to a calibrated eval
  model. Treat absolute scores as relative, reproducible ordering signals.
- The engine is a lifecycle + scores store around Phase 6 evaluation metrics; it
  does not run live evals against production traffic or paid providers.
- Per-case `passed` uses a fixed 0.75 correctness cutoff — a documented policy
  constant, not a tuned threshold.