# NEXUS Reliability — Verification, Recovery & Evaluation

Phase 6 gives NEXUS a correctness and resilience layer: determine whether work was **right**, detect failures, **recover** when safe, keep a human in the loop when not, and **measure** how the whole system performs.

> Core transition: *"successful execution" no longer implies "successful outcome."*

This document is the reference for the three Phase 6 packages, their integration points, the failure-recovery state machine, the safety model, and the evaluation framework.

---

## Table of contents

1. [Architecture principles](#architecture-principles)
2. [Verification](#verification)
3. [Recovery](#recovery)
4. [Escalation (human-in-the-loop)](#escalation-human-in-the-loop)
5. [Evaluation framework](#evaluation-framework)
6. [Database model](#database-model)
7. [API surface](#api-surface)
8. [Frontend](#frontend)
9. [Safety model](#safety-model)
10. [Testing & deterministic demos](#testing--deterministic-demos)

---

## Architecture principles

- **Layered.** FastAPI routes → application services → `app/verification/` + `app/recovery/` + `app/evaluation/` → existing runtime systems. No business logic in routes, models, migrations, or the frontend.
- **Single reusable verification layer.** Verification is *called by* the Agent-loop hooks, Workflow Engine, and Orchestrator — never duplicated inside them.
- **Deterministic first.** Low risk = schema-only; medium = schema + deterministic; high = + independent agent + due escalation. Model-based strategies are one input, never treated as truth.
- **Verifier independence.** A verifier is not, by default, the same agent that produced the work.
- **Bounded, policy-driven recovery.** Never `while not success: retry()`. Budgets, max attempts, and idempotency gate every retry.
- **Provider-independent.** Mock providers and sync-inline execution make all of it testable with no paid API in CI.
- **Small dedicated modules, explicit state machines, structured exceptions, correlation IDs** (`execution_id` / `orchestration_id` / `workflow_id` propagate through every table).

---

## Verification

Located in `apps/api/app/verification/`.

### Lifecycle

`VerificationService.verify(...)`:

1. Loads/derives a `VerificationPolicy` (or skips when `required=False`).
2. Selects strategies for the risk level (`select_strategies(risk_level)`).
3. Runs each strategy over the candidate `result_data` → individual `StrategyOutcome`s.
4. Aggregates into a single `VerificationResult` (status, score, confidence, reason, passed/failed criteria, evidence, recommendations).
5. Persists a `VerificationRun` + `VerificationResult` (and, on PASS, a verified-fact memory via the memory hook).

### Statuses

`pass` | `fail` | `partial` | `uncertain` | `skipped`. Aggregation takes the minimum status across non-skipped strategies, weighted by confidence.

### The six strategies

| Strategy | Module | Purpose | Notes |
|---|---|---|---|
| `deterministic` | `strategies/deterministic.py` | Literal/equality/comparison/presence checks | Cheap, exact, zero-LLM |
| `schema` | `strategies/schema.py` | Require fields, types, enums, min/max | Enters all results at high risk |
| `rules` | `strategies/rules.py` | Config list of `{path, op, expected}` | Safe, non-executable operator vocabulary — rejects `eval` |
| `tool` | `strategies/tool.py` | Re-runs a trusted tool via `ToolExecutor` | Uses the **same** `PermissionService` context — never bypasses rights |
| `model` | `strategies/model.py` | Concise structured evaluator | Concise evidence only, no chain-of-thought |
| `independent_agent` | `strategies/independent_agent.py` | A capability-distinct agent verifies | Minimal, un-biased context (output + criteria only) |

### Policies

`VerificationPolicy` (`{required, strategies, minimum_score, minimum_confidence, max_attempts, allowed_verifier_types, escalation_behavior, retry_behavior}`) is validated eagerly against unknown strategy names and persisted per-scope (`verification_policies` row with `scope_type`/`scope_id`). A `WorkflowStep` or `Orchestration` can carry a `verification_policy` (JSON) so verification is enforced inline during execution.

### Integration points (all additive, gated by policy)

- **Workflow Engine** — after an `agent_task`/`tool_action` step produces output, if a policy is present, `VerificationService` runs; a FAIL below the minimum score fails the step and its workflow. The verdict is exposed as `steps.<name>.verification.score` to conditional branches. (`StepExecution.verification_run_id`).
- **Orchestrator** — each task's output is verified when the orchestration policy requires it; a failing subtask recovers independently without restarting unrelated agents. Final synthesis can also be verified.
- **Memory** — on PASS, a single verified-fact memory (`store_reliability_memory`); on repeated failure, a failure-pattern/recovery memory. Zero or one per outcome — never noisy writes.

---

## Recovery

Located in `apps/api/app/recovery/`.

### Failure taxonomy

Categories: `validation_failure`, `model_failure`, `tool_failure`, `timeout`, `permission_failure`, `invalid_input`, `invalid_output`, `dependency_failure`, `memory_failure`, `communication_failure`, `resource_limit`, `verification_failure`, `system_failure`, `unknown`. Severity: `low` | `medium` | `high` | `critical`.

### Diagnosis

`HeuristicDiagnoser` maps evidence (exception type + execution status + tool-call status + error text) → category + severity + `retryable` + recommended strategy + confidence + evidence. Deterministic and rule-based.

### The recovery engine & state machine

```
detected → classified → recovery_planned → recovering →
    { retrying | replanning | fallback } → reverified
terminal: recovered | failed | escalated | aborted | partially_recovered
```

`RecoveryEngine.recover(execution_id, ...)` drives the lifecycle, recording each `RecoveryAttempt` and its transitions (the recovery timeline).

### The ten strategies

| Strategy | When | Notes |
|---|---|---|
| `retry` | transient, idempotent | gated by budget |
| `retry_with_backoff` | transient | recorded delay |
| `retry_with_modified_input` | wrong inputs | |
| `replan` | plan is wrong | may invoke Phase-5 `DeterministicPlanner` |
| `fallback_agent` | capability gap | via `CapabilityAgentSelector` |
| `fallback_tool` | primary tool failed | via `FallbackToolRegistry` through the same permission path |
| `skip` | non-blocking | continue cleanly |
| `partial_completion` | some work completed | `PartialCompletionBuilder` |
| `escalate` | unsafe / exhausted | persistent `escalations` row |
| `abort` | unrecoverable | terminal |

Choice is bounded by `ExecutionBudget` + `max_attempts` via `BudgetTracker` and `RetrySafety`.

### Safety (non-negotiable)

- Recovery never broadens permissions.
- Retry is gated by Phase-3 `IdempotencyTag`: `side_effecting`/`non_idempotent` steps never blind-retry.
- High-risk/destructive tools never blind-retry → escalate.
- Budget exhaustion stops recovery and records the reason.
- Escalation cannot be auto-approved by the agent.

---

## Escalation (human-in-the-loop)

`EscalationService` persists `escalations` rows (`PendingHumanReview → Approved | Rejected`) with an issue, category, severity, and context. There is no outbound notification infrastructure (a deliberate boundary). `approve(id, reason)`, `reject(id, reason)`, `list(state)`. The web UI's **Escalations** page is the review surface.

---

## Evaluation framework

Located in `apps/api/app/evaluation/`.

- **`metrics.py`** — pure named functions: `task_success_rate`, `verification_pass_rate`, `recovery_success_rate`, `retry_rate`, `failure_rate`, `intervention_rate`, `completion_time`, `token_cost`, `efficiency`.
- **`dataset.py`** — a deterministic 8-case suite (reasoning, structured JSON, tool selection, tool-failure recovery, multi-agent collaboration, verification failure, retry, partial completion), all mock-provider fixtures — no paid API.
- **`runner.py`** — `EvaluationRunner` executes cases → persists `evaluations`, `evaluation_runs`, `evaluation_cases`, `evaluation_results`, `evaluation_metrics`. Sync-inline, deterministic ordering.
- **`comparison.py`** — `compare_runs(a, b)` → score delta + per-metric deltas + `regression` flag.
- **`regression.py`** — `RegressionDetector.flag(prev, curr, threshold)` → `REGRESSION_DETECTED | OK`. No auto-rollback.

---

## Database model

Migration chain `0001 → … → 0007_verification_recovery_evaluation → 0008_integration_verification` (head). New tables (in `app/db/models/reliability.py`):

- `verification_policies`, `verification_runs`, `verification_results`
- `failure_diagnoses`, `recovery_plans`, `recovery_attempts`, `escalations`
- `evaluations`, `evaluation_runs`, `evaluation_cases`, `evaluation_results`, `evaluation_metrics`

Plus two added columns: `WorkflowStep.verification_policy`, `StepExecution.verification_run_id`.

---

## API surface

All under `/api/v1`:

| Endpoint | Purpose |
|---|---|
| `GET/POST /verifications` | list runs / trigger verification |
| `GET /verifications/{id}` · `GET /verifications/runs/{run_id}` | fetch result / run |
| `POST/GET /verifications/policies(/{id})` | policy CRUD |
| `GET /recoveries/attempts/{id}` | fetch an attempt |
| `GET /recoveries/executions/{id}` · `POST /recoveries/executions/{id}/recover` | list / trigger recovery |
| `GET /recoveries/diagnoses/executions/{id}` · `…/plans/…` | diagnosis / plan |
| `GET /escalations` · `GET /escalations/{id}` · `POST …/{id}/approve` · `POST …/{id}/reject` | escalation review |
| `GET /evaluations` · `GET /evaluations/{id}` | evaluations |
| `GET/POST /evaluations/runs` · `GET /runs/{run_id}` · `GET /runs/{run_id}/results` · `GET /runs/compare` · `GET /regression/check` | runs + compare + regression |

Literal routes are declared before `/{id}` param routes.

---

## Frontend

`apps/web` additions under the **Verification & Reliability** nav group:

- **Verifications** — pass/fail/partial/uncertain rates, average score, status filter, verify-by-execution panel.
- **Recoveries** — attempt stats (recovered/escalated/failed), latest diagnosis, a **recovery state-machine timeline** per attempt, recover-by-execution panel.
- **Evaluations** — run scores and metric bars, per-case results, run comparison + regression check, run-default-suite.
- **Escalations** — approve/reject pending human reviews with an optional decision note.

Shared via `types.ts`, `api.ts`, `StatusBadge.tsx` (new Phase 6 statuses + failure-category colors), and matched by a `types-phase6.test.ts`.

---

## Testing & deterministic demos

`apps/api/tests/` — 55 new suites across verification, recovery, evaluation, safety, integration, and two demos:

- **Self-Healing Workflow** — a workflow runs a research agent, an intentional tool failure is diagnosed, a bounded retry/fallback recovers it, and the result passes independent verification.
- **Multi-Agent Verification** — a research agent produces analysis, a fact-checker verifies independently, an incorrect claim fails verification, the research agent revises, and re-verification passes.

Both are deterministic (mock providers, sync-inline) and assert the full lifecycle is persisted and observable.

---

## Related

- [docs/architecture.md](architecture.md) — system architecture & data model
- [docs/roadmap.md](roadmap.md) — phase history (Phase 6 completed)
- [docs/orchestration.md](orchestration.md) — Phase 5 multi-agent orchestration