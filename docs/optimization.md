# NEXUS — Optimization Engine

What the Phase 12 optimization engine actually delivers, how to run it, and what it
honestly does not claim. Part of the Phase 12 suite — see [phase-12.md](phase-12.md)
for the umbrella, and the sibling docs [simulation.md](simulation.md),
[experimentation.md](experimentation.md), [benchmarking.md](benchmarking.md),
[agent-marketplace.md](agent-marketplace.md), and
[closed-loop-optimization.md](closed-loop-optimization.md).

---

## 1. High-level

The optimization engine (`app/phase12/optimization.py`) solves **weighted
multi-objective problems** — candidates ranked by a total weighted score — with a
strict standing rule: **optimization proposes, governance decides**. Every
candidate is evaluated against the Phase 11 `PolicyEngine` (action
`optimization.apply`) and `ResourceGovernanceService` (the `cost` budget) *before*
it is scored; a policy-denied or over-budget candidate is marked invalid and is
never proposed. The best candidate becomes an **explainable recommendation** carrying
the **§46 ten-question explainability block** (what / why / alternatives /
constraints / why-this-candidate / expected benefit / expected cost / risks /
assumptions / approval). Applying one requires human approval via
`ApprovalGateManager` — there is **no auto-production-replacement**.

Strategies are deterministic and provider-neutral (no external SaaS):

- `greedy` (`GreedyStrategy`) — start from defaults and nudge each variable in the
  objective's maximizing direction.
- `exhaustive` (`ExhaustiveStrategy`) — bounded combinatorial search over each
  variable's 5-point sample grid (`itertools.product`).
- `ranking` (`RankingStrategy`) — a scoring-signal seam for externally-ranked
  candidates (interface in place; the concrete exhaustive/greedy grids are what the
  engine currently generates).

New strategies plug in behind the `OptimizerStrategy` protocol. `max_candidates=500`
bounds a run — an over-wide search raises rather than exploding.

## 2. What landed

- **`OptimizationEngine`** (`optimization.py`) — `create_problem` / `list_problems` /
  `get_problem` / `run_problem` / `run_results` / `recommend` /
  `approve_rec` / `reject_rec`.
- **Model vocabulary** — `Objective` (metric + `minimize`/`maximize` + weight),
  `Variable` (kind `float`/`integer`, low/high/default/options; integer variables
  never produce fractional candidates), `Constraint` (a callable checked per
  candidate — a failing constraint rejects the candidate before scoring).
- **Governance in the evaluator** — `_evaluate()` runs `policy_check`
  (default: `PolicyEngine.evaluate(identity_id=None, action="optimization.apply", …)`)
  and `resource_limits("cost", company_id)` first. Candidate validity is decided by
  policy (deny / require_approval ⇒ invalid), budget (expected `budget` > effective
  `cost` limit ⇒ invalid), then user/engine constraints. Only valid candidates are
  scored (`weighted maximize/minimize` over the objectives) and persisted.
- **§46 explainability block** — `_explainability_block()` writes all ten keys onto
  every `OptimizationRecommendation.explanation_json`. The stored recommendation
  also carries `expected_benefit_json`, `expected_cost_json`
  (*"modeled cost, to be confirmed before execution"*), `risk_json`, and
  `assumptions_json`. Status lifecycle: `proposed → pending_approval → approved /
  rejected`, with `approved_by`/`approved_at`/`rejected_reason` recorded.
- **Determinism + persistence** — per-run `optimization_runs` rows (strategy,
  result JSON with best values + score), per-candidate `optimization_candidates`
  (values + per-objective scores) and `optimization_scores` rows; problems and
  recommendations (`.objective_json`, `explanation_json` …) are JSON-rich, enum-light
  storage in the project's convention.
- **API** (`app/phase12/api/optimization.py`) — mounted at `/api/v1/optimization`
  (see §4).
- **Migration** — `0014_phase12_sim_opt_mkt` adds the optimization tables
  (`optimization_problems`, `optimization_variables`, `optimization_constraints`,
  `optimization_objectives`, `optimization_runs`, `optimization_candidates`,
  `optimization_scores`, `optimization_recommendations`, `optimization_lessons`)
  additively.

## 3. Governance details

- **Policy first, then budget, then constraints** — the ordering is load-bearing:
  a disallowed candidate is rejected before any scoring, so the optimizer can never
  present a policy-violating "best".
- **Recommendation ≠ application** — `recommend()` only persists a `proposed`
  recommendation. `approve_rec()` marks it `approved` (recording the approver).
  Applying a decision to production systems is the closed-loop's job
  ([closed-loop-optimization.md](closed-loop-optimization.md)), gated by an
  `ApprovalGateManager` gate that authorizes exactly one action, once; Phase 12
  itself never mutates production rows.
- **Per-day budget** — the `optimization_candidates` category is registered with
  Phase 12 governance (`governance.py`), configured through the Phase 11
  resource-limit APIs. Unlimited until an operator sets a limit; the engine's own
  `max_candidates` ceiling is always active.

## 4. API map (`/api/v1/optimization`)

```text
GET    /optimization/problems                       list problems (?company_id)
POST   /optimization/problems                       create (objectives / variables / constraints)
GET    /optimization/problems/{id}                  get one problem
POST   /optimization/problems/{id}/run              run the problem (strategy from problem)
GET    /optimization/runs/{run_id}                  get a run
GET    /optimization/runs/{run_id}/results          ranked candidates + best_candidate
GET    /optimization/recommendations                list (?company_id, ?status)
POST   /optimization/runs/{run_id}/recommend        create the §46 explainable recommendation
GET    /optimization/recommendations/{id}           get one recommendation
POST   /optimization/recommendations/{id}/approve   mark approved (records approver)
POST   /optimization/recommendations/{id}/reject    mark rejected (records optional reason)
```

Wire-level constraints in `POST /problems` are informational specs (name +
description); real bounds are enforced at run time by `PolicyEngine` +
`ResourceGovernanceService`, so candidates can never violate policy or resource
limits even if a constraint is left unchecked.

## 5. How to verify

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_phase12_optimization.py -q

# Migration round-trip (revision 0014_phase12_sim_opt_mkt)
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade 0013 && .venv/bin/alembic upgrade head

# Live smoke (server on 127.0.0.1:8000)
.venv/bin/python -m scripts.smoke_api --phase 12
```

The Phase 12 demo (Part 2: agent optimization against measured benchmark scores;
Part 3: headcount/budget allocation under a budget-cap constraint + a governing
resource limit) asserts every §46 key is present, that the best candidate respects
its hard constraints, and that the recommendation starts `proposed`:

```bash
cd apps/api
.venv/bin/python -m scripts.seed_simulation_optimization [--reset]
```

## 6. Known honest limits

- **Optimization proposes; governance decides.** A recommendation is an *estimate*
  scored against modeled candidates — it is never auto-applied, never a promise
  about real outcomes. Expected cost is explicitly *"modeled cost, to be confirmed
  before execution"* and expected benefit is a modeled score, not a guarantee.
- **Explainability is structural, not causal** — the §46 block explains *why this
  candidate scored highest among the evaluated set* under the stated objectives and
  constraints. It does not claim a learned causal model of the business.
- Strategy selection is manual (a problem carries its `strategy`, defaulting to
  `greedy`); there is no automatic strategy search or portfolio optimization.
- `ranking` currently exists as the strategy seam; the generated candidate grids
  today come from `greedy` and `exhaustive`.
- Deterministic default models: sample grids and scores are fixed without a seed;
  reproducibility is by construction, not by calibration.
- Phase 12 budgets are DB-configured (unlimited until an operator sets per-company
  limits through the Phase 11 governance API).