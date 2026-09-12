# NEXUS Autonomous Startup Engine

Phase 9 gives NEXUS a **mission-driven autonomous startup layer** above the AI Company Layer: a group declares a mission, NEXUS plans a startup around it (strategy → startup plan → organizational blueprint → workforce), bootstraps a company, and then runs **governed operating cycles** — observe → assess → plan → prioritize → allocate → execute → verify → measure → learn → replan — that are provably traceable, never exceed a bounded autonomy envelope, and keep a human gate on every high-impact action.

> Core posture: *the engine decides and acts within a per-company autonomy policy; anything beyond it parks at an approval gate for one specific action, one time.*

This document is the reference for the Phase 9 packages (`apps/api/app/startup/`), the operating engine, the autonomy/governance model, the mission graph, the API surface, the frontend, the safety boundaries, and the deterministic demo + tests.

---

## Table of contents

1. [Architecture principles](#architecture-principles)
2. [Mission system](#mission-system)
3. [Startup planning & bootstrap](#startup-planning--bootstrap)
4. [Operating cycle](#operating-cycle)
5. [Autonomy & governance](#autonomy--governance)
6. [Feedback, lessons & replanning](#feedback-lessons--replanning)
7. [Observation & state](#observation--state)
8. [Mission graph & traceability](#mission-graph--traceability)
9. [Database model](#database-model)
10. [API surface](#api-surface)
11. [Frontend](#frontend)
12. [Safety model & global limits](#safety-model--global-limits)
13. [Testing & deterministic demo](#testing--deterministic-demo)
14. [Phase 10 boundary](#phase-10-boundary)

---

## Architecture principles

- **Layered.** FastAPI routes → `app/startup/` services → the existing Phase 1–8 systems. No business logic in routes, models, migrations, or the frontend.
- **Reuse over duplication.** The engine composes infrastructure it already owns instead of re-implementing it:
  - provisioning → `EmployeeManager` (Phase 7) + `CompanyManager.add_membership` (Phase 8)
  - execution → `TaskService` + `create_runtime(db).execute_task` + `VerificationService` (Phase 6)
  - budgets/policies/KPIs → `BudgetManager`, `PolicyResolver`, `KPIService` (Phase 8)
  - decisions → `DecisionManager` (Phase 8)
  - lessons → `MemoryService` / `CompanyMemoryService` namespaces (Phase 4)
  - events → `OrgEventLogger` via `StartupEventLogger` (`app/startup/events.py`)
  There is **no second** execution, memory, company, employee, or decision system.
- **Deterministic first.** Every analyzer, planner, validator, and engine has a deterministic, provider-free implementation (the default). `Model*` variants exist behind the `ModelProvider` Protocol but the demo, the tests, and CI never require a paid API.
- **Bounded autonomy is structural.** A human approval gate — persisting in `approval_gates` and scoped to *one* requested action — is required for anything the policy does not auto-allow. Some actions (finance, hiring, external) are `block` in every level and not negotiable.
- **Traceability is a first-class graph.** Entities record provenance edges (`mission_graph_edges`), so every product, project, execution, KPI, and feedback item answers "what mission, strategy, and objective made this exist?"
- **Immutable cycle records.** Each `operating_cycles` row is a complete, ordered, immutable timeline of stages, decisions, actions, KPIs, failures, recoveries, approvals, and resource usage — written once, never mutated.

---

## Mission system

Located in `app/startup/mission.py` (service), `analyze.py`, `validate.py`, `strategy.py`, `plans.py`. A **mission** (`missions` table) is the top of the traceability graph and the unit of company engagement.

- **Create** a mission for a company with a title and mission statement (extended by target market, desired outcome, constraints, assumptions, success criteria, priority). Missions are company-scoped — every read/lifecycle call requires `company_id`.
- **Lifecycle.** `draft → analyzing → planned → active ⇄ paused → blocked → completed | failed | cancelled`. Transitions are enforced; e.g. you cannot `plan` an unvalidated mission, and you cannot `activate` a mission without an approved startup plan.
- **Analyze** decomposes the mission into objectives, required capabilities, risks, unknowns, constraints, assumptions, and success criteria (`DeterministicMissionAnalyzer` — rule-based extraction; `ModelMissionAnalyzer` via `ModelProvider.structured_output`).
- **Validate** runs the completeness/safety checklist (§5): required fields, conflicting constraints, unrealistic resource asks, missing success criteria, missing target outcome, autonomy-scope violations, policy/budget conflicts. Returns a structured `ValidationResult` (errors + warnings). A mission with errors cannot be planned.
- **Plan** derives a **strategic plan** (vision, objectives, priorities, milestones, dependencies, capabilities, resource estimates, success metrics) and then a **startup plan** from it.

---

## Startup planning & bootstrap

Located in `app/startup/strategy.py`, `plans.py`, `blueprint.py`, `workforce.py`, `provision.py`, `bootstrap.py`, `objectives.py` (objective decomposition) and `products.py`/`projects.py`.

A **startup plan** (`startup_plans`) is the fully-earned answer to "what will we actually run." It carries business / product / market / organization / operational objectives, milestones, the **organizational blueprint** (departments → roles → authority → skills → reporting → staffing → objectives → KPIs → budgets — configurable, never a hardcoded single org chart), the **workforce plan** (role / skills / count / priority / workload / budget / authority / department demand), initial products and projects, KPI targets, budget allocation, execution priorities, and the approval requirements it will need.

- **Startup plan lifecycle.** `draft → under_review → approved → bootstrapping → active ⇄ paused → completed | cancelled`. `validate` gates plan completeness; `approve` requires the plan itself to validate and the parent mission to be planned. `bootstrap` runs a `COMPANY_BOOTSTRAP_APPROVAL` gate, then builds the company.
- **Provisioning** creates employees through Phase 7's `EmployeeManager` (identity + role + skills + responsibilities + tools + permissions + policies + workload) and places them via `CompanyManager.add_membership`, assigning initial goals. Provisioning is gated by the autonomy policy and hard-capped by `MAX_AUTONOMOUS_EMPLOYEES` (`startup_max_employees`).
- **Bootstrap** stands up the company from the approved plan using Phase 8 primitives only: `CompanyManager.create`, departments, roles, memberships, initial goals, KPIs, budgets. No parallel company entities.
- **Products & projects** are seeded from the plan and thereafter follow governed lifecycles: products `idea → discovery → validation → planning → building → testing → ready_for_launch → launched → measuring → iterating` (+ `paused`/`retired`), with `launch` passing a `PRODUCT_LAUNCH_APPROVAL` gate; projects `planned → active → blocked → completed | cancelled` with priorities, budgets, milestones, dependencies, and success criteria, feeding tasks through `TaskService`.

---

## Operating cycle

Located in `app/startup/cycle.py`. The **OperatingEngine** runs the canonical loop:

```text
observe → assess → plan → prioritize → allocate → execute → verify → measure → learn → replan
```

- **Synchronous, governed, immutable.** `run_cycle(company_id, mission_id)` executes the loop synchronously (mirroring the Phase 6 sync-inline execution pattern) and writes a single immutable `operating_cycles` row with its ordered `stages` timeline plus decisions, actions, KPIs, failures, recovery, approvals, and resource usage. There is **no new scheduler or worker** in Phase 9.
- **Governed by the autonomy policy.** Every action in a cycle consults `AutonomyService`; anything not auto-allowed parks the cycle at `awaiting_approval` with an `approval_gates` row and a specific `approve` endpoint. Cycle status stays in the agreed `OperatingCycleStatus` vocabulary (`initializing/observing/assessing/planning/awaiting_approval/executing/verifying/measuring/replanning/completed/blocked/failed/cancelled`).
- **Bounded by global limits.** A cycle is force-checkpointed at `MAX_OPERATING_CYCLE_DURATION` minutes and never exceeds `MAX_AUTONOMOUS_ACTIONS_PER_CYCLE` autonomous actions (`startup_max_operating_cycle_duration`, `startup_max_autonomous_actions_per_cycle`).
- **EXECUTE** runs work through the existing engines: single tasks via `TaskService` + runtime execute; multi-step via `WorkflowService`; multi-agent via `OrchestrationService`. **VERIFY** routes results through the Phase 6 `VerificationService`; **RECOVERY** is the Phase 6 state machine (failures that are safe and bounded are retried/fallback-recovered; the rest escalate). **MEASURE** records phase values via `KPIService`.

---

## Autonomy & governance

Located in `app/startup/autonomy.py` and `gates.py`.

- **Per-company autonomy level.** `autonomy_policies` holds one row per company: `AutonomyLevel` (`manual | assisted | bounded_autonomy | high_autonomy`, default `bounded_autonomy`) plus an **allow matrix** and hard caps (`max_employees`, `max_departments`, `max_budget`, `max_concurrent_work`) and `require_approval_for`. `GET /autonomy/{company_id}/policy` returns the **effective** allow matrix (per-level defaults merged with any company overrides — the verdicts the engine actually enforces) plus the `never_allowed` structural block list.
- **Three outcomes per action.** `AutonomyService.can_auto_act(action, company_id)` returns one of:
  - `allow` — runs automatically (still subject to budget/policy/authority checks),
  - `require_approval` — must first obtain an **approved** `approval_gates` row,
  - `block` — never autonomous for this company, ever.
- **Some actions are always blocked** — autonomous finance, hiring/firing, real-world legal/external side effects are `block` in every level. Bounded autonomy is structural, not a slider a company can set to "off".
- **Approval gates** (`approval_gates`) are created for every required-approval action. Each gate records `gate_type` (mission / strategy / company_bootstrap / workforce / budget / product_launch / high_risk_action / major_strategic_change), `risk_level`, the exact `requested_action`, `rationale`, affected entities, and resource impact. `approve`/`reject` (with expiry) authorize **exactly one** governed action — approving a gate never widens future autonomy. Gates emit `APPROVAL_REQUESTED / GRANTED / REJECTED` events.

---

## Feedback, lessons & replanning

Located in `app/startup/feedback.py`, `lessons.py`, `replan.py`.

- **Feedback** is synthesized from observable signals (KPI variance, task/verification/recovery/evaluation outcomes, project/product status, resource utilization, risks/alerts). Each `startup_feedback` row carries a confidence score and a recommendation, but **a recommendation is never auto-executed**.
- **Lessons** are recorded to `startup_lessons` (lesson / decision_outcome / failed_assumption / success_pattern / process_improvement / strategic_insight) and mirrored into the Phase 4 Memory System via `MemoryService`/`CompanyMemoryService` namespaces — one memory store, no second DB.
- **Replanning** (`ReplanningEngine`) triggers on: KPI underperformance, milestone failure, resource shortage, execution failure, verification failure, major risk, budget threshold, changed assumptions, blockage, or validation failure. Responses are bounded (`continue / reprioritize / reassign / replan / reduce_scope / increase_scope / pause_project / abort_project / create_new_project / request_approval / escalate`) and capped at `MAX_REPLANNING_ATTEMPTS` (`startup_max_replanning_attempts`). A replan may propose a priority re-ordering, a resource re-allocation, or a new/revised startup plan — all still subject to the autonomy policy.

---

## Observation & state

Located in `app/startup/observe.py`. **Observation** aggregates real, authoritative state — goals, KPI values (`KPIService`), budgets (`BudgetManager`), performance (`PerformanceAggregator`), verification/recovery rates, risks/alerts, product/project status — into a `CompanyStateSnapshot` (`company_state_snapshots`): an `overall_score`, per-dimension scores, and a per-dimension **explanation** naming the concrete metric behind the number. There are no fabricated health scores; every dimension is backed by observable data. Snapshots are point-in-time records (immutable), and `GET /startup/{company_id}/state/history` returns the sequence.

---

## Mission graph & traceability

Located in `app/startup/graph.py` and `app/startup/types.py`.

- **Nodes** are first-class entities: `mission / strategy / objective / goal / product / project / employee / task / execution / kpi / decision / feedback`.
- **Relations** are typed: `derived_from / depends_on / assigned_to / executed_by / measured_by / blocked_by / generated_by / improves / triggers`.
- Edges are recorded as entities are created (no separate provenance system) and stored in `mission_graph_edges` (unique on `(source_type, source_id, target_type, target_id, relation)`).
- `GET /missions/{mission_id}/graph` returns the mission's edges; `GET /missions/{mission_id}/graph/trace/{node_type}/{node_id}` walks ancestor edges to answer *"why does this thing exist?"* — returning the chain back to its origin mission.

---

## Database model

One additive migration: **`0011_autonomous_startup_engine`** (down_revision `0010_company_layer`); no drops or alters of Phase 0–8 tables. Models live in `app/db/models/startup.py` (StrEnum enums, native `VARCHAR` convention like the rest of the schema; JSON payloads via `JSON`; `company_id` FKs for isolation; indexes on `company_id`, `(source_type, source_id)`, `(target_type, target_id)`).

| Table | Purpose |
| --- | --- |
| `missions` | mission root: statement, desired outcome, target market, constraints/assumptions/success criteria, priority, lifecycle status, `analysis`/`validation` JSON |
| `strategic_plans` | vision, objectives, priorities, milestones, dependencies, capabilities, resource estimates, success metrics |
| `startup_plans` | full startup plan: objectives, blueprint + workforce demand, initial products/projects, KPI targets, budget allocation, approval requirements, lifecycle status |
| `organizational_blueprints` | configurable org structure (departments → roles → authority → skills → staffing → KPIs → budgets) |
| `workforce_plans` | role/skill/count/priority/workload/budget/authority demand + approval policy |
| `products` | product lifecycle, target users, budget, success metrics, launch criteria, validation |
| `startup_projects` | project lifecycle, priority, budget, milestones, dependencies, success criteria |
| `execution_plans` | objective scope, projects/employees/workflows/orchestrations/tasks, verification policy, approval gates, resource limits |
| `operating_cycles` | **immutable** cycle record: status lifecycle, ordered stages, decisions, actions, KPIs, failures, recovery, approvals, resource usage, outcome |
| `company_state_snapshots` | point-in-time overall/dimension scores + explanations (observation) |
| `startup_feedback` | feedback records (source, category, observation, impact, confidence, recommendation) |
| `startup_lessons` | lessons mirrored into Phase 4 memory |
| `approval_gates` | governance: gate type, risk, requested action, affected entities, resource impact, status + expiry |
| `mission_graph_edges` | typed traceability edges (unique tuple) |
| `autonomy_policies` | one per company: level, allow matrix, hard caps, require-approval list |
| `resource_allocations` | budget/capacity/concurrency/token/tool/time allocations |
| `priority_decisions` | explainable priority score + factors per target |

---

## API surface

Six routers registered in `app/api/v1/router.py`. Company/mission scoping is a **query parameter** (`?company_id=` / `?mission_id=`) — never a path param — matching the company-layer convention.

**`/missions`** — `POST/GET ""`, `GET/PUT /{mission_id}`, `POST /{mission_id}/analyze`, `.../validate`, `.../plan`, `.../activate`, `.../pause`, `.../cancel`, `GET /{mission_id}/graph`, `GET /{mission_id}/graph/trace/{node_type}/{node_id}`.

**`/startup-plans`** — `POST/GET ""` (company- **and** mission-scoped — the mission must belong to the presented `?company_id`, so a foreign caller gets `404`, never the plan), `GET/PUT /{plan_id}`, `POST /{plan_id}/validate`, `.../approve`, `.../bootstrap`, `.../execute`.

**`/startup`** — `POST/GET /{company_id}/cycles`, `GET /{company_id}/cycles/{cycle_id}`, `POST /{company_id}/cycles/{cycle_id}/execute|approve|cancel`, `POST /{company_id}/replan`, `GET /{company_id}/state`, `GET /{company_id}/state/history`, `GET /{company_id}/next-actions`, `GET/POST /{company_id}/feedback`.

**`/products`** — `POST/GET ""` (company-scoped), `GET/PUT /{product_id}`, `POST /{product_id}/validate|launch|status`.

**`/startup-projects`** — `POST/GET ""` (company-scoped), `GET/PUT /{project_id}`, `POST /{project_id}/status`.

**`/autonomy`** — `GET/PUT /{company_id}/policy`, `GET /{company_id}/approval-gates`, `GET /{company_id}/approval-gates/pending`, `GET /{company_id}/approval-gates/{gate_id}`, `POST /{company_id}/approval-gates/{gate_id}/approve|reject`.

All reads are company- or mission-scoped; lifecycle and validation errors return `400` with a `detail`; creates return `201`. Every read endpoint verifies the parent company/mission exists (`404` otherwise), and cross-company access returns `404` — never a leak.

---

## Frontend

Located in `apps/web/src/app/startup/` with `StartupShell` (`_components/StartupShell.tsx`), a client layout context that holds the selected **company** (persisted to `localStorage`; defaults to the first company), scopes every fetch by it, provides a `href()` helper, and records the plan→mission mapping so plan pages can resolve mission-scoped fetches after navigation. This avoids sprinkling `useSearchParams`/`Suspense` across every page. Pages follow the repo convention: `"use client"`, `useEffect` + `let cancelled`, a `LoadState` discriminated union, `Link`/`StatusBadge`, and `@/` aliases.

- `/startup` — overview: current company state (overall + top dimension), attention banner for pending approvals, latest cycle, lists of missions/products/projects/feedback, next actions.
- `/startup/missions` + `/startup/missions/[id]` — create + list; detail with Analysis/Validation panels, startup-plan entry, mission graph edges, operating cycles, and Analyze / Validate / Plan / Activate / Pause / Cancel controls.
- `/startup/plans/[id]` — startup plan detail with objectives, blueprint, KPIs, and Validate / Approve / Bootstrap / Run cycle controls.
- `/startup/operations` + `/startup/operations/[cycleId]` — run a cycle for a chosen mission; cycle list; detail with the 10-stage timeline, failures/recovery, approvals, decisions, and outcome.
- `/startup/products` + `/startup/products/[id]` — product lifecycle, validation, launch.
- `/startup/projects` + `/startup/projects/[id]` — project lifecycle and objectives.
- `/startup/approvals` — autonomy policy card (level, caps, per-action matrix) + approval-gate table with Approve/Reject.
- `/startup/mission-graph` — edges view with relation filter.
- `/startup/feedback` — feedback records + "Evaluate replan".

The legacy `/missions` page is a thin `redirect("/startup/missions")`. The "Autonomous Startup" entry leads `NAV_SECTIONS`.

---

## Safety model & global limits

Hard limits live in `app/core/config.py` (`Settings`, Phase 9 block) and are enforced by `AutonomyService`, the provisioner, the bootstrapper, and the cycle engine:

| Setting | Default | Meaning |
| --- | --- | --- |
| `startup_default_autonomy_level` | `bounded_autonomy` | default level for a new company |
| `startup_require_approval_for_high_risk` | `True` | high-risk actions without a gate are denied |
| `startup_max_operating_cycle_duration` | `90` (min) | force-checkpoint before this |
| `startup_max_autonomous_actions_per_cycle` | `25` | hard cap on autonomy in one cycle |
| `startup_max_employees` | `20` | `MAX_AUTONOMOUS_EMPLOYEES` per company |
| `startup_max_budget` | `1500.0` | `MAX_STARTUP_BUDGET` (USD) per company |
| `startup_max_projects_per_plan` | `10` | cap on seeded projects |
| `startup_max_replanning_attempts` | `3` | replan attempt cap |
| `startup_max_concurrent_operations` | `5` | concurrency cap |

Structural invariants:

- **No unrestricted autonomy.** Every autonomous action is checked; `block` always exists and respects global caps regardless of the company's level.
- **No autonomous finance or hiring/firing**, no self-modification of NEXUS, no real-world external actions (network/email/legal) — Phase 9 acts only inside the NEXUS runtime.
- **Approval gates authorize one action, once.** Granting a gate never widens the allow matrix.
- **Deterministic by default** — the system is judged by what observably happened (verified executions, recorded KPIs, immutable cycles), not by what an unverified model claimed.

---

## Testing & deterministic demo

Backend tests live in `apps/api/tests/test_startup_*.py` (`test_startup_mission`, `_strategy`, `_plan`, `_workforce`, `_product_project`, `_cycle`, `_autonomy`, `_replanning`, `_traceability`, `_security`, `_demo`) using the repo's `conftest.py` fixtures (`db_engine`/`db`/`api_client`/`phase6_settings`) and MockProvider executions — ~85 startup tests on top of the full regression suite, all green with no paid API.

Frontend: `apps/web/src/lib/__tests__/types-phase9.test.ts` covers the Phase 9 unions and full fixtures (98 web tests pass alongside the phase test files).

**Deterministic demo** — `scripts/seed_autonomous_startup.py` (idempotent; reuses an existing company/mission of the same name, or `--reset` to start clean):

```bash
.venv/bin/python -m scripts.seed_autonomous_startup
```

Runs the full §51 chain with MockProvider: company → mission → analyze → validate → strategic plan (derived) → startup plan → approve → **company bootstrap** (departments, roles, memberships, goals, KPIs, budgets) → **workforce provisioning** → products → projects → objectives → tasks → **operating cycle** with an **injected execution failure that verification catches, recovery retries, and a fallback agent resolves** → KPIs → state snapshot → **feedback** → **replan** (priority change) → **approval gate** (product-dev budget +20%, human-approved) → continued operation → mission-graph query → final state summary.

---

## Verification commands

Backend (`apps/api`):

```bash
alembic upgrade head          # applies 0011_autonomous_startup_engine (additive)
.venv/bin/pytest -q            # all startup + regression tests green
ruff check app tests && ruff format --check app tests
```

Frontend (`apps/web`):

```bash
npx tsc --noEmit && npm run lint && npm run build
npm run test -- --run
```

Live end-to-end: boot Postgres on 5433 + uvicorn on 8000, run the demo via the API, and confirm per-company isolation (a mission of company A is not readable as company B).

---

## Phase 10 boundary

Phase 9 operates **entirely inside the NEXUS runtime**. It runs tasks through the existing engines, records immutable cycles and snapshots, and governs everything through approval gates. **Phase 10 does not exist yet** — browser/computer-use, external integrations, autonomous external publishing, self-modification, or any widening of the autonomy envelope is explicitly out of scope. The autonomy model in Phase 9 is designed so that raising a level or opening a new capability later is a deliberate, documented, gated change — never a side effect of a feature.
