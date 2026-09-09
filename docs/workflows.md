# NEXUS — Workflow Orchestration

> **Phase 3.** Workflows turn the Agent Runtime and Tool System into coordinated
> pipelines: sequences of steps — agent tasks, tool actions, conditions, and
> delays — that pass structured input and output between one another, run in
> dependency order, and can be retried, timed out, paused, cancelled, and
> triggered automatically.

---

## 1. Overview

A **workflow** is a named, versioned graph of **steps**. Each step is one of
four kinds:

| Step type      | What it does                                                        |
| -------------- | ------------------------------------------------------------------- |
| `agent_task`   | Runs an agent through `AgentRuntime.execute_task()` with mapped input |
| `tool_action`  | Invokes a registered tool via the permission-gated `ToolExecutor`    |
| `condition`    | Evaluates a safe condition against workflow state; gates downstream steps |
| `delay`        | Pauses the run for a fixed number of seconds                         |

Steps declare **dependencies** on other steps by name. A step becomes **ready**
only when all of its dependencies have completed, and the engine runs steps in
dependency order (topologically sorted) — fully deterministic, no multi-threading.

Each execution produces a **step trace**: one `StepExecution` per step recording
status, attempt number, input, output, error, and duration, plus a final
`WorkflowExecution` summary.

Three confirmed architecture decisions shape the implementation:

- **DB-as-queue, in-process worker/scheduler** — no Redis at runtime. Pending
  executions are rows in `workflow_executions`; an in-process worker thread
  claims them and an in-process scheduler thread fires due triggers.
- **Dependency-aware, sequential execution** — steps run in dependency order,
  one at a time, deterministically.
- **Worker/scheduler auto-start with the API** — gated by the
  `WORKFLOW_WORKER_ENABLED` setting, so tests and minimal deploys can leave it
  off.

---

## 2. Execution Lifecycle

```
create workflow → add steps → validate → activate
                                             │
                                             ▼
        manual execute │ scheduled trigger │ event trigger │ webhook
                                             │
                                             ▼
                    WorkflowExecution (status = queued)
                                             │
                      worker claims (status = running)
                                             ▼
                     engine.execute(execution_id)
        ┌──────────────────────────────────────────────┐
        │ for each step in dependency order:           │
        │   resolve input mapping from state           │
        │   run step  (agent / tool / condition / delay)│
        │   store output in state["steps"][name]        │
        │   update StepExecution                        │
        └──────────────────────────────────────────────┘
                                             │
                          completed / failed / cancelled / timed_out
```

Workflow **statuses**: `draft` → `active` → `paused`. Only `active` workflows
can be executed. Execution **statuses**: `queued`, `running`, `completed`,
`failed`, `cancelled`, `timed_out`. Step **statuses**: `pending`, `ready`,
`running`, `completed`, `failed`, `skipped`, `cancelled`, `timed_out`.

### State & data flow between steps

Execution state is a single JSON document:

```jsonc
{
  "input": { "topic": "AI trends", "region": "APAC" }, // from execution input_data
  "steps": {
    "research": { "output": { "lead_count": 75, "summary": "..." }, "status": "completed" }
  }
}
```

A step's **input mapping** pulls values from this state by path. Example step
`configuration` for an agent task:

```json
{
  "agent_id": "<agent-uuid>",
  "input_mapping": {
    "topic": "input.topic",
    "lead_count_so_far": "steps.research.output.lead_count"
  }
}
```

The engine resolves every mapping against the current state before running the
step, so later steps receive structured output from earlier ones. Condition and
tool steps use the same mapping mechanism.

---

## 3. Step Types in Detail

### `agent_task`

- `configuration.agent_id` — the agent to run (must be `active`).
- `configuration.input_mapping` — paths → task input.

The engine creates a transient task, assigns it to the agent, and runs it
through `AgentRuntime.execute_task()`. The agent's provider is resolved from
the registry on each execution (`provider="mock"` needs no key). The produced
`AgentResult.output_data` becomes the step's output.

### `tool_action`

- `configuration.tool_name` — a registered tool (e.g. `calculator`).
- `configuration.arguments` — explicit arguments, passed verbatim.

The engine invokes `ToolExecutor.execute()`, which validates → authorizes
(per-agent `PermissionContext`) → runs (with a per-tool timeout) → persists a
`ToolCallRecord`. A `denied` result fails the workflow; a tool resolution or
validation failure is reported as an error.

### `condition`

- `configuration.condition` — either a leaf `{field, op, value}` or a nested
  `{and: [...]}` / `{or: [...]}` tree.

Supported ops: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`,
`not_contains`. Evaluation is a **safe** interpreter — no `eval()`, no arbitrary
code — over a resolved path into state.

```json
{ "condition": { "field": "steps.research.output.lead_count", "op": "gt", "value": 50 } }
```

If a condition evaluates false, the step is marked **skipped** and every
downstream dependent step is also skipped (gated, deterministic branching).

### `delay`

- `configuration.duration` — seconds to pause. The engine checks cancellation
  while sleeping so a cancelled run stops promptly.

---

## 4. Retry, Timeout, and Idempotency

Each step carries optional `retry_policy` and `timeout_seconds`.

- **Timeout**: a step exceeding `timeout_seconds` is marked `timed_out` and the
  workflow fails.
- **Retry policy**: `{ "max_attempts": 3, "backoff": "exponential" | "fixed",
  "delay": 1, "retry_on": ["<error-substrings>"] }`. A failed step is retried up
  to `max_attempts` with backoff when permitted.
- **Idempotency** (`idempotency` tag: `read_only`, `idempotent`,
  `non_idempotent`, `side_effecting`): only `read_only` or `idempotent` steps
  are eligible for automatic retry. `non_idempotent` / `side_effecting` steps
  are not retried automatically (a retry on a side-effecting step may double a
  payment, send two emails, etc.), and the validator warns if an unsafe retry
  policy is configured for them.

---

## 5. Triggers

A workflow may expose **triggers**. Only triggers on `active` workflows with
`enabled = true` fire.

| Type       | Fired by                                                        |
| ---------- | --------------------------------------------------------------- |
| `schedule` | The scheduler on `next_run_at`; `configuration` supports `cron` (via `croniter`) or `interval` (seconds). |
| `event`    | An external `event_name` (service method / API)                   |
| `webhook`  | An inbound webhook call for the trigger                           |

Each firing creates a new `WorkflowExecution` (status `queued`) and advances
`next_run_at`. Manual execution (`POST /{id}/execute`) is always available.

---

## 6. Worker & Scheduler

- **`WorkflowWorker`** — an in-process daemon thread that polls a **DB-backed
  queue** (`workflow_executions` where `status='queued'`). It claims a row
  atomically (`SELECT … FOR UPDATE SKIP LOCKED` on Postgres; `SELECT + UPDATE`
  on SQLite), marks it `running`, and hands it to `WorkflowEngine`. On startup
  it **recovers stale** runs: executions stuck `running` past the timeout are
  marked `timed_out`, so a restart never leaves ghost work.
- **`WorkflowScheduler`** — an in-process daemon thread that polls
  `workflow_triggers` joined to `workflow` for enabled triggers whose
  `next_run_at` has passed, fires them, and advances `next_run_at`.

Both start automatically in the FastAPI lifespan when
`WORKFLOW_WORKER_ENABLED=true` (off in tests and by default in the API config;
on in local dev/prod). This gives durable, restart-safe orchestration with zero
extra runtime infrastructure.

---

## 7. API Reference (summary)

All under `/api/v1/workflows`.

| Method + path                          | Purpose                                   |
| -------------------------------------- | ----------------------------------------- |
| `GET /workflows`                       | List workflows (optional `?status=`)       |
| `POST /workflows`                      | Create a workflow                          |
| `GET /workflows/{id}`                  | Get a workflow                             |
| `PATCH /workflows/{id}`                | Update a workflow                          |
| `DELETE /workflows/{id}`               | Delete a workflow                          |
| `POST /workflows/{id}/activate`        | Validates then activates (`active`)        |
| `POST /workflows/{id}/pause`           | Pauses (`paused`)                          |
| `GET /workflows/{id}/validate`         | Validate the step graph (cycles, refs)     |
| `GET /workflows/{id}/steps`            | List steps                                 |
| `POST /workflows/{id}/steps`           | Add a step                                 |
| `PATCH /workflows/steps/{step_id}`     | Update a step                              |
| `DELETE /workflows/steps/{step_id}`    | Remove a step                              |
| `GET /workflows/{id}/triggers`         | List triggers                              |
| `POST /workflows/{id}/triggers`        | Add a trigger                              |
| `DELETE /workflows/triggers/{id}`      | Remove a trigger                           |
| `POST /workflows/{id}/execute`         | Queue (or run inline) an execution         |
| `GET /workflows/{id}/executions`       | List an workflow's executions              |
| `GET /workflows/executions/{eid}`      | Get one execution                          |
| `GET /workflows/executions/{eid}/steps`| Get one execution's step trace             |
| `POST /workflows/executions/{eid}/cancel` | Cancel a queued/running execution       |

`POST /{id}/execute` runs inline (returns a completed execution) when the
`workflow_execute_sync` setting is on — which is how the test suite exercises
the full engine deterministically — and otherwise queues the execution for the
worker.

---

## 8. Example — Daily Research Workflow

An end-to-end flow: research → gate on volume → notify if a threshold is met.

```bash
# 1. Create an active mock agent to do the research step
curl -X POST localhost:8000/api/v1/agents -H 'Content-Type: application/json' \
  -d '{"name":"researcher","role":"researcher","status":"active","provider":"mock","model_name":"mock-model"}'

# 2. Create the workflow
WF=$(curl -X POST localhost:8000/api/v1/workflows -H 'Content-Type: application/json' \
  -d '{"name":"Daily research digest","description":"Research, gate, notify."}' | jq -r .id)

# 3. Add steps: research → condition → notify (condition depends on research, notify on condition)
curl -X POST localhost:8000/api/v1/workflows/$WF/steps -H 'Content-Type: application/json' \
  -d "{\"name\":\"research\",\"step_type\":\"agent_task\",\"configuration\":{\"agent_id\":\"<agent_id>\",\"input_mapping\":{\"topic\":\"input.topic\"}}}"
curl -X POST localhost:8000/api/v1/workflows/$WF/steps -H 'Content-Type: application/json' \
  -d '{"name":"gate","step_type":"condition","dependencies":["research"],\
       "configuration":{"condition":{"field":"steps.research.output.lead_count","op":"gt","value":50}}}'
curl -X POST localhost:8000/api/v1/workflows/$WF/steps -H 'Content-Type: application/json' \
  -d '{"name":"notify","step_type":"tool_action","dependencies":["gate"],\
       "configuration":{"tool_name":"calculator","arguments":{"expression":"40 + 2"}}}'

# 4. Activate and execute with input
curl -X POST localhost:8000/api/v1/workflows/$WF/activate
curl -X POST localhost:8000/api/v1/workflows/$WF/execute -H 'Content-Type: application/json' \
  -d '{"input_data":{"topic":"AI trends"}}'

# 5. Inspect the step trace
EXEC_ID=$(curl localhost:8000/api/v1/workflows/$WF/executions | jq -r '.[0].id')
curl localhost:8000/api/v1/workflows/executions/$EXEC_ID/steps
```

If the mock agent returns `lead_count > 50` in its output, `notify` runs; if not,
`gate` is skipped and `notify` is skipped too — deterministic branching verified
in the step trace.