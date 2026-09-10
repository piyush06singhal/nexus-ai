# NEXUS — Multi-Agent Orchestration Reference

Phase 5 moves NEXUS from **single-agent task execution** to **multiple specialized agents coordinating on a shared objective**. Where Phase 3's workflows compose *steps*, and Phase 4 gave agents *memory*, Phase 5 assembles a **team**: a planner decomposes an objective into tasks, a capability-based selector assigns each task to the best-available agent, and an orchestrator runs the team — in parallel and in dependency order — over a controlled communication bus, then aggregates, conflict-checks, and synthesizes a verified final result.

The orchestration engine **reuses the Agent Runtime (Phase 1), Tool Executor + permissions (Phase 2), workflow engine/retry semantics (Phase 3), and Memory (Phase 4)** rather than duplicating any of them. It is provider-independent and demo-driven: the deterministic planner/synthesizer and mock providers run the whole loop with no paid API. Every orchestration is observable — tasks, assignments, messages, results, reviews, and a timeline are all persisted and queryable.

---

## 1. Architecture

```
 FastAPI routes  →  orchestration_service  →  app/orchestration/ engine  →  Agent Runtime → tools / memory
        (thin)            (CRUD + lifecycle)      (planner, selector, orchestrator, ...)
```

Layering is strict: no orchestration logic lives in routes, models, or the frontend. The engine's modules are small and individually testable:

| Module (`app/orchestration/`) | Responsibility |
| ---- | ---- |
| `types.py` | Domain dataclasses (`PlanTask`, `ExecutionPlan`, `AgentSelection`, `Conflict`) + structured exceptions. |
| `capabilities.py` | Canonical capability vocabulary, role→capability map, tool-permission-derived capabilities, `resolve_agent_capabilities()`. |
| `planner.py` | `Planner` protocol + `DeterministicPlanner` — objective → validated `ExecutionPlan`. |
| `selector.py` | `AgentSelector` protocol + `CapabilityAgentSelector` — task → best agent. |
| `state_machine.py` | Explicit legal transitions for orchestration, task, and assignment statuses. |
| `messages.py` | `AgentMessageType` enum. |
| `bus.py` | `AgentMessageBus` — authorized, DB-backed inter-agent messaging. |
| `context.py` | Task-appropriate input context construction + shared-context store. |
| `conflicts.py` | `ConflictDetector` protocol + `NumericConflictDetector`. |
| `synthesizer.py` | `ResultSynthesizer` — result aggregation + source attribution. |
| `review.py` | `AgentReviewService` — request/review/verdict with iteration limits. |
| `orchestrator.py` | The engine — drives the full lifecycle synchronously. |

Exceptions raised by the engine are structured (`OrchestrationError` base with `PlannerError`, `NoAgentAvailableError`, `SynthesisError`, `ConflictDetectionError`, `CommunicationError`, `AssignmentExecutionError`, `InvalidTransitionError`) and every state write is validated by the state machine — a status can never silently drift into an inconsistent state.

---

## 2. Lifecycle & state machine

An orchestration moves through a strict lifecycle (`app/orchestration/state_machine.py`); any illegal transition raises `InvalidTransitionError`:

```
created → planning → planned → assigning → running → synthesizing → completed
                               │                  ├──→ failed
                               │                  ├──→ partially_completed
                               │                  └──→ cancelled
created → cancelled
```

- **`planner`** — `created → planning → planned`. The planner emits the task graph; plan validation (references, cycles) happens before any agent runs.
- **`selector`** — `planned → assigning`. Assign an agent to each task; a task with no matching agent is marked failed and skipped, and if no task can run the orchestration fails.
- **`executor`** — `assigning → running`. Run ready tasks (bounded thread pool), persist results, and submit dependents whose prerequisites completed.
- **`synthesizer`** — `running → synthesizing → completed`. Aggregate results, detect conflicts, synthesize the final result.
- **Terminal states** — `completed` (all depended-on tasks ran), `partially_completed` (some tasks failed/skipped but a usable result exists), `failed` (no usable result), `cancelled`.

Tasks have their own lifecycle: `pending → ready → running → completed`, with legal paths to `skipped` / `cancelled` / `failed`. Assignments follow `pending → assigned → running → completed` with `failed` / `cancelled` / `timed_out` terminal states.

---

## 3. Planner & task decomposition

`app/orchestration/planner.py::DeterministicPlanner.create_plan(objective, available_agents, context)` returns an `ExecutionPlan` — a validated structured object, never free-form model JSON. `app/orchestration/validator.py`-style checks (unique names, valid dependency references, cycle-freedom) run before any agent is assigned.

Decomposition rules are deterministic:

- A **market / competitive-analysis template** (objective mentions `market`, `competitive`, `report`, `analyze`, `write`) emits four tasks — **Research**, **Analysis**, **Fact-check** (parallel, no dependencies) → then **Writer** (depends on all three). This is the spec's canonical "AI Market Research Team" demo.
- Any other objective falls back to a **single task** with `required_capabilities: ["general"]`.

Each `PlanTask` carries `name`, `description`, `required_capabilities`, and `dependencies`. The produced `execution_graph` is persisted as JSON on the orchestration.

### Capabilities

`app/orchestration/capabilities.py` defines the canonical capability keys — `research`, `analysis`, `fact_checking`, `writing`, `data_processing`, `summarization`, `general` — mapped from agent **roles** (e.g. role `researcher` → `research`) and unioned with capabilities derived from the agent's **granted tool permissions** via `PermissionService.list_for_agent`. `resolve_agent_capabilities(agent, db)` returns the union, so agents expose matching metadata with no schema change on the `agents` table.

---

## 4. Agent selection

`app/orchestration/selector.py::CapabilityAgentSelector.select(task, available_agents)` assigns an agent to a task deterministically:

- Candidates must be `active` and executable.
- A candidate matches when `set(task.required_capabilities) ⊆ set(agent_capabilities)`.
- Among matches, pick the **highest coverage score** (`len(matched) / len(required)`); tie-break by the **least-used** agent (round-robin) to spread load.
- Enforces `max_agents_per_orchestration`. If none match, raise `NoAgentAvailableError` (the orchestrator marks the task failed/skipped rather than crashing the run).

`AgentSelection` records `agent_id`, `matched_capabilities`, and `score`; the assignment is persisted in the `agent_assignments` table and reflected on the task's `agent_id`. Selection is behind an `AgentSelector` protocol so smarter strategies can later be plugged in without changing callers.

---

## 5. Communication bus & collaboration

`app/orchestration/messages.py` defines message kinds (`task_assignment`, `task_result`, `request_information`, `information_response`, `status_update`, `error`, `review_request`, `review_result`). `app/orchestration/bus.py::AgentMessageBus` persists every message to the `agent_messages` table and **enforces authorization** — only agents that belong to the orchestration can send/receive; a foreign orchestration id is rejected. Messages carry an optional `correlation_id` (request↔response threading) and a `task_id` scope.

The **CollaborationView** in the UI renders this as a message + review thread between agents, so you can see exactly who requested information from whom and how reviews flowed.

---

## 6. Shared context & memory integration

`app/orchestration/context.py` builds a **task-appropriate** input — the objective, the task's description, and any relevant shared facts/decisions — *not* the whole orchestration state. Dependent tasks additionally receive the relevant prior task outputs.

Shared facts are stored in the `orchestration_context` table with a `kind` (`shared_fact` / `decision` / `constraint` / `intermediate_result`) and an optional `agent_id` (private when set). The system integrates with Phase 4 Memory by persisting orchestration results as structured memories under the `orchestration` namespace (see `docs/memory.md`), and each agent task runs through the standard runtime so it retains its own per-agent memory scope.

---

## 7. Execution: parallel & sequential

`app/orchestration/orchestrator.py::Orchestrator.execute(orchestration_id)` drives the lifecycle synchronously (mirroring `WorkflowEngine`):

1. Load the orchestration; validate it is in a rumnable state (`created`/`running`).
2. **Plan** — call the planner, validate, persist `orchestration_tasks` + execution graph.
3. **Select** — assign agents, mark unassignable tasks failed.
4. **Run** — execute ready tasks in a **bounded `ThreadPoolExecutor`** (`min(max_concurrent_tasks, max_parallel_agents)` from config). Each worker opens a **fresh DB session** via `session_factory`, marks the assignment/task running, calls the reusable `AgentRuntime` (temp Task + assign + `runtime.execute_task`, exactly like `WorkflowEngine._run_agent_task_step`), persists the result + messages + shared context. When a worker finishes, ready dependents are submitted. **A failed task marks only its dependents `skipped`; independent tasks keep running** (no blanket failure). Cancellation is checked after each batch.
5. **Synthesize** — aggregate results → `ConflictDetector` → `ResultSynthesizer` → persist `final_result` + metrics.
6. Move to the appropriate terminal status with `started_at`/`completed_at`/`duration_ms` and a metrics JSON (task counts, success/failure, retries, messages, parallelism).

The constructor is dependency-injected: `Orchestrator(session_factory, planner=None, selector=None, synthesizer=None, conflict_detector=None, settings=None)`. A `max_concurrent_tasks=1` mode gives fully deterministic execution order for tests.

`app/services/orchestration_service.py::OrchestrationService` wraps this as the API-facing controller — `create`, `get`, `list`, `delete` (non-running), `execute` (runs the engine inline for the deterministic path), `cancel` (state-machine-guarded; already-completed tasks stay completed), and all read serializers (`tasks`, `assignments`, `messages`, `results`, `context`, `reviews`, `timeline`).

---

## 8. Aggregation, conflict detection & synthesis

`app/orchestration/synthesizer.py::ResultSynthesizer.synthesize(...)` produces the spec's structured final result:

```json
{
  "status": "completed",
  "summary": "Market analysis with source attribution; no conflicts.",
  "findings":   [{ "finding": "...", "agent_id": "...", "task_id": "..." }],
  "sources":    [{ "agent_id": "...", "task_id": "...", "content": "..." }],
  "conflicts":  [],
  "incomplete_tasks": [],
  "agent_contributions": { "<agent_id>": "<summary>" }
}
```

- **Source attribution** — every finding/source records the producing agent and task; nothing is invented — only data actually present in the results.
- **Conflict detection** (`app/orchestration/conflicts.py::NumericConflictDetector`) — detects two agents reporting the same key with substantially different numeric values (`|a−b| / max(|a|,|b|) > threshold`, default `0.2`) or contradictory boolean/status fields, emitting `Conflict` records. Unresolved conflicts are surfaced in `final_result.conflicts` and mentioned in the summary.
- **Incomplete tasks** are listed explicitly so a partial result is never mistaken for a complete one.

---

## 9. Agent review

`app/orchestration/review.py::AgentReviewService` provides a review foundation: `request(task_id, reviewer, content)`, `complete(review_id, verdict, content)`, `list(orchestration_id)`. Verdicts are `pending | approved | rejected | request_revision`. `max_review_iterations` bounds revision loops and a review timeout prevents hung reviews — no infinite loops. Reviews are stored in the `agent_reviews` table and surfaced through the CollaborationView.

---

## 10. Failure, retry & cancellation

- **Task failure** — a failed task records its error; its dependents become `skipped`; independent siblings continue. Net result is `partially_completed` (or `failed` when no usable result emerges).
- **Retry** — assignments track `attempt_number`; agent execution goes through the same Agent Runtime as Phase 1 tasks, so any runtime/tool retry semantics carry over.
- **Cancellation** — `POST /{id}/cancel` is state-machine-guarded: only non-terminal orchestrations can be cancelled. Already-completed tasks remain completed; queued/pending work does not start. The run records `cancelled`.

---

## 11. Resource limits

`app/orchestration/policies.py::OrchestrationLimits.from_settings()` derives limits from config, enforced by the orchestrator and selector before work begins:

| Config | Default | Meaning |
| ------ | ------- | ------- |
| `ORCHESTRATION_MAX_AGENTS` | `20` | Max agents participating in one orchestration. |
| `ORCHESTRATION_MAX_TASKS` | `50` | Max decomposed tasks per orchestration (checked at plan time — a bigger plan is rejected before any agent runs). |
| `ORCHESTRATION_MAX_PARALLEL_AGENTS` / `_TASKS` | `5` | Thread-pool size for parallel execution. |
| `ORCHESTRATION_MAX_EXECUTION_DURATION_SECONDS` | `3600` | Wall-clock cap for a run. |
| `ORCHESTRATION_MAX_EXECUTION_ITERATIONS` | `100` | Cap on execution batches. |
| `ORCHESTRATION_MAX_MESSAGES_PER_ORCHESTRATION` | `500` | Cap on bus messages. |
| `ORCHESTRATION_MAX_REVIEW_ITERATIONS` | `3` | Cap on review revision loops. |
| `ORCHESTRATION_CONFLICT_NUMERIC_THRESHOLD` | `0.2` | Relative-diff threshold that flags a numeric conflict. |
| `ORCHESTRATION_MEMORY_NAMESPACE` | `orchestration` | Memory namespace used by orchestration context persistence. |

Hard limits are enforced **per orchestration**, so a runaway plan or chatty team can never exhaust a shared pool.

---

## 12. Security model

- **Isolated context** — each task receives only the shared facts + prior outputs relevant to it, never the full orchestration state or another agent's private context.
- **Authorized bus** — the message bus rejects messages that don't belong to the orchestration's participant set; cross-orchestration communication is impossible by construction.
- **Tool permissions** — agent capabilities include only the tools the agent is *allowed* to use (`PermissionService.list_for_agent`), so a task can never request a capability the agent isn't permissioned for.
- **Memory isolation** — orchestration results are written to the `orchestration` namespace; per-agent memory stays scoped to the agent, preserving Phase 4's namespace/owner isolation.
- **No privileged network access** — the engine is provider-independent and makes no external calls on its own; side effects only occur through the permission-gated tool executor.

---

## 13. Workflow integration

An orchestration can be embedded as a **step type** in a Phase 3 workflow:

- `WorkflowStepType.ORCHESTRATION` — added to the workflow step-type enum (string-valued, no migration).
- `app/workflow/validator.py` — requires the step's `configuration.orchestration_id`.
- `app/workflow/engine.py::_run_orchestration_step` — loads the orchestration, runs it (inline), and returns `{orchestration_status, final_result, ...}` into the workflow state for the next step.

This composes the two coordination layers: a workflow can *call* an orchestration as one of its steps, and an orchestration's tasks are themselves agent tasks.

---

## 14. API reference

All routes live under `/api/v1/orchestrations` (router in `app/api/v1/endpoints/orchestrations.py`).

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/orchestrations` | Create with `{objective, strategy?}`. `201`. |
| `GET` | `/orchestrations` | List, filter by `status`. Returns `{items, total}`. |
| `GET` | `/orchestrations/{id}` | Fetch one orchestration. |
| `DELETE` | `/orchestrations/{id}` | Delete (non-running). `204`. |
| `POST` | `/orchestrations/{id}/execute` | Run to completion (inline/deterministic). |
| `POST` | `/orchestrations/{id}/cancel` | State-machine-guarded cancel. |
| `GET` | `/orchestrations/{id}/tasks` | Decomposed tasks (status, capabilities, outputs). |
| `GET` | `/orchestrations/{id}/assignments` | Agent assignments. |
| `GET` | `/orchestrations/{id}/messages` | Inter-agent messages. |
| `GET` | `/orchestrations/{id}/results` | Aggregated per-task results. |
| `GET` | `/orchestrations/{id}/context` | Shared context entries. |
| `GET` | `/orchestrations/{id}/timeline` | Observability timeline (created → plan → assignments → completions → synthesis → terminal). |
| `POST` | `/orchestrations/{id}/reviews` | Request an agent review. `201`. |
| `POST` | `/orchestrations/{id}/reviews/{review_id}/complete` | Record a verdict. |
| `GET` | `/orchestrations/{id}/reviews` | List reviews for an orchestration. |

### Example — the AI Market Research Team demo

```bash
# 1. Create four active mock agents with the market-team roles
for spec in \
  'researcher|researcher' 'analyst|analyst' 'fact_checker|fact_checker' 'writer|writer'; do
  role=${spec#*|}; name=${spec%|*}
  curl -X POST localhost:8000/api/v1/agents -H 'Content-Type: application/json' \
    -d "{\"name\":\"$name\",\"role\":\"$role\",\"status\":\"active\",\"provider\":\"mock\",\"model_name\":\"mock-model\",\"model_params\":{\"reply\":\"{\\\"summary\\\":\\\"$name done\\\",\\\"output\\\":{\\\"key\\\":\\\"value\\\"}}\"}}"
done

# 2. Create and run a market analysis orchestration
ORCH=$(curl -X POST localhost:8000/api/v1/orchestrations -H 'Content-Type: application/json' \
  -d '{"objective":"analyze the competitive market and write a report"}' | jq -r .id)
curl -X POST localhost:8000/api/v1/orchestrations/$ORCH/execute

# 3. Inspect the team's work
curl localhost:8000/api/v1/orchestrations/$ORCH/tasks
curl localhost:8000/api/v1/orchestrations/$ORCH/timeline
curl localhost:8000/api/v1/orchestrations/$ORCH | jq .final_result
```

---

## 15. Configuration

All orchestration settings live on the `Settings` singleton (environment variables / `.env`). The key limits and thresholds are listed in [§11](#11-resource-limits); general settings:

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `ORCHESTRATION_WORKER_ENABLED` | `false` | Auto-start an orchestration worker in the API lifespan. |
| `ORCHESTRATION_EXECUTE_SYNC` | `false` | Run `POST /{id}/execute` inline (`true` in the test suite). |
| `ORCHESTRATION_DEFAULT_STRATEGY` | `deterministic` | Default planning strategy. |
| `ORCHESTRATION_TOKEN_BUDGET` / `COST_BUDGET` | `None` | Reserved per-run budget caps. |

---

## 16. Frontend

The **Orchestrations** nav section (`/orchestrations`) joins the dashboard between Workflows and Tools.

- **List page** (`apps/web/src/app/orchestrations/page.tsx`) — objective, status badge, agent/task counts, a completion progress bar, run/cancel actions, a status filter, and a **Create & run** form that seeds the objective and immediately executes a team.
- **Detail page** (`apps/web/src/app/orchestrations/[id]/page.tsx`) — objective + status, the **final result** (summary, attributed findings, conflicts), the **ExecutionGraph** (task dependency tree with status-colored nodes, assigned agent, and expandable I/O), **metrics**, the **CollaborationView** (agent messages + reviews), a **timeline**, per-task **results**, **shared context**, and the raw execution graph.
- **Components** — `ExecutionGraph.tsx` and `CollaborationView.tsx` in `apps/web/src/components/orchestration/`, built with plain divs + the shared `StatusBadge` (no new dependencies), matching `WorkflowVisualization`.
- **API client** (`apps/web/src/lib/api.ts`) — `fetchOrchestrations`, `createOrchestration`, `getOrchestration`, `executeOrchestration`, `cancelOrchestration`, and the read helpers for tasks/assignments/messages/results/context/reviews/timeline; shared types in `apps/web/src/lib/types.ts`.

---

## 17. Storage (migration `0006_orchestrations`)

Seven tables under `app/db/models/orchestration.py`, registered in `app/db/models/__init__.py`, all FK-cascading from `orchestrations`:

- **`orchestrations`** — objective, status, strategy, selected_agents, execution_graph, final_result, error, metrics, timestamps.
- **`orchestration_tasks`** — name, required_capabilities, dependencies, status, agent_id, input_context, output_data, result_summary, attempt_number, error, timing.
- **`agent_assignments`** — task_id, agent_id, role, instructions, priority, dependencies, status, input/output, agent_execution_id.
- **`agent_messages`** — sender/recipient agent, message_type, content, metadata, correlation_id, task_id.
- **`orchestration_results`** — task_id, assignment_id, agent_id, content, structured_data, confidence, metadata.
- **`orchestration_context`** — key, value (JSON), kind, optional agent_id (private).
- **`agent_reviews`** — task_id, reviewer/reviewee agent, request/response content, verdict, iteration.

Indexes cover `orchestration_id` on each child, `(status)`, `(created_at)`, `correlation_id`, and `(orchestration_id, created_at)` for message/context ordering.

---

## 18. Tests

Phase 5 ships a dedicated, comprehensive suite under `apps/api/tests/test_orchestration_*.py` (unit + integration, SQLite-backed, mock providers — no paid API):

- `state_machine`, `planner`, `selector`, `bus`, `conflicts`, `synthesizer`, `review` — module-level unit tests.
- `execution` — single/multi-agent, dependency ordering, parallel, failure/retry/cancellation, resource limits, security.
- `integration` — Orchestrator → Agent Runtime → Tool Executor → Memory end-to-end, and a Workflow with an `ORCHESTRATION` step.
- `demo` — the deterministic **AI Market Research Team** scenario proving the full pipeline (decompose → parallel team → writer → synthesized final result with attribution).

---

## 19. Observability & scale

- **Timeline** — every orchestration exposes an ordered event trace (plan → assignments → completions → synthesis → terminal), so a run is fully reconstructable.
- **Structured errors + correlation** — domain exceptions and logging are tagged with the orchestration id.
- **Metrics** — completed orchestrations carry counts (tasks total/completed/failed, agents used, messages, retries, parallelism, duration).
- **Scale path** — the deterministic planner/selector are behind protocols; concurrent run execution and a distributed worker are future work over the same seven-table model.