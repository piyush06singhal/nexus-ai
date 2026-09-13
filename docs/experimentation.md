# NEXUS — Experimentation

What the Phase 12 experiment engine actually delivers, how to run it, and what it
honestly does not claim. Part of the Phase 12 suite — see [phase-12.md](phase-12.md)
for the umbrella, and the sibling docs [simulation.md](simulation.md),
[optimization.md](optimization.md), [benchmarking.md](benchmarking.md),
[agent-marketplace.md](agent-marketplace.md), and
[closed-loop-optimization.md](closed-loop-optimization.md).

---

## 1. High-level

The experiment engine (`app/phase12/experiments.py`) runs **controlled what-if
analyses** (baseline + variants) under an **approval gate**, with **honest
conclusions**. An experiment is the formal sibling of ad-hoc scenarios: you state a
hypothesis, a sample size, a metric list, a baseline, and one or more variant
configs; you submit it for approval; on approval it runs; when it completes you
record a result whose conclusion is one of **WINNER / LOSER / INCONCLUSIVE** (`ExperimentConclusion`,
capitalized in the UI) together with an explicit `confidence` declaration and
`limitations` — never an overstated significance claim.

Lifecycle: `DRAFT → PENDING_APPROVAL → APPROVED → RUNNING → COMPLETED | STOPPED |
CANCELLED`. Experiments are **modeled what-if analyses — they never modify
production state**.

## 2. What landed

- **`ExperimentEngine`** (`experiments.py`) — `create_experiment` /
  `list_experiments` / `get_experiment` / `get_variants` / `submit_for_approval` /
  `approve` / `run_experiment` / `complete_experiment` / `stop_experiment` /
  `cancel_experiment` / `record_metric` / `get_results` / `get_metrics`.
- **Lifecycle is state-guarded** — submit requires `DRAFT`; approve requires
  `PENDING_APPROVAL`; run requires `DRAFT` or `APPROVED`; complete/stop require
  `RUNNING`; illegal transitions raise `ExperimentError` rather than drift.
  The experiment record carries an `approval_gate_id` for traceability.
- **Baseline + variants** — `ExperimentVariant` rows (name + `config_json`,
  `is_baseline` flag) hang off the `Experiment`.
- **Metrics** — `record_metric()` persists `ExperimentMetric` rows, attached to
  the experiment and linked to the most recent `ExperimentRun` when one exists,
  with per-variant linkage and an explicit `sample_size`.
- **Honest results** — `complete_experiment()` requires `RUNNING`, flips the
  experiment to `COMPLETED`, and persists an `ExperimentResult` carrying
  `conclusion` (winner / loser / inconclusive), optional `winning_variant_id`,
  the experiment's `sample_size`, plus `metrics_json`, `confidence_json`,
  `assumptions_json`, and `limitations_json`. The default conclusion is
  `inconclusive` — proving the instrument's bias toward honesty.
- **API** (`app/phase12/api/experiments.py`) — mounted at `/api/v1/experiments`
  (see §4).
- **Migration** — `0014_phase12_sim_opt_mkt` adds `experiments`,
  `experiment_variants`, `experiment_runs`, `experiment_metrics`,
  `experiment_results` additively.

## 3. Governance

- **Approval-gated** — `PENDING_APPROVAL` is a real state, not a label: an
  experiment cannot be run from `DRAFT` in production flows without passing through
  approval (the run endpoint requires `APPROVED` or `DRAFT`; the intended round trip
  is `submit → approve → run`). The same `ApprovalGateManager` infrastructure as
  Phase 9/11 backs the gate, and separation-of-duties / self-approval hardening
  compose automatically when `auth_enabled`.
- **Isolated by default** — experiments never modify production state; they are
  modeled analyses over the experiment's declared baseline and variants.
- **Per-day budget** — `experiment_runs` is a registered Phase 12 resource category
  (`governance.py`), configured through the Phase 11 resource-limit APIs —
  unlimited until an operator sets a limit.

## 4. API map (`/api/v1/experiments`)

```text
GET    /experiments                         list experiments (?company_id)
POST   /experiments                         create (hypothesis, sample_size, metrics,
                                            baseline, variants[])
GET    /experiments/{id}                    get one experiment
POST   /experiments/{id}/submit             DRAFT → PENDING_APPROVAL
POST   /experiments/{id}/approve            PENDING_APPROVAL → APPROVED
POST   /experiments/{id}/run                → RUNNING
POST   /experiments/{id}/stop               RUNNING → STOPPED
POST   /experiments/{id}/complete           RUNNING → COMPLETED + ExperimentResult
                                            (conclusion, winning_variant_id, metrics,
                                             confidence, assumptions, limitations)
GET    /experiments/{id}/results            list ExperimentResult rows
```

## 5. How to verify

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_phase12_experiments.py -q

# Migration round-trip (revision 0014_phase12_sim_opt_mkt)
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade 0013 && .venv/bin/alembic upgrade head

# Live smoke (server on 127.0.0.1:8000)
.venv/bin/python -m scripts.smoke_api --phase 12
```

The Phase 12 demo seeds experiment data as part of the deterministic suite; the
experiment lifecycle is exercised end-to-end in `tests/test_phase12_experiments.py`
(draft → submit → approve → run → record metrics → complete with a conclusion that
carries confidence + limitations).

## 6. Known honest limits

- **Experiments are modeled what-if analyses, not live A/B traffic.** Nothing here
  splits real production users between variants; the experiment clock, sample size,
  and results are what the operator records into the lifecycle.
- **Conclusions are honest by construction** — `WINNER / LOSER / INCONCLUSIVE`
  with explicit sample size, confidence, and limitations on every result. The
  engine does not compute statistical significance for you: it stores the
  declarations you provide and defaults to `inconclusive` rather than overstating a
  winner. Do not read a recorded `conclusion` as a machine-proven effect.
- Approval gating composes the Phase 9/11 gates — those are enforcement-solid; the
  experiment engine itself records the gate id but does not re-derive
  authorization (that is the enforcement layer's job).