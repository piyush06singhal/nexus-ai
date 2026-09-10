# NEXUS

**An Autonomous AI Workforce & Company OS.**

NEXUS lets you hand a high-level business objective to a system of AI agents that plans, coordinates, and executes toward it. It combines three long-term ambitions into one platform:

1. **AI Company in a Box** — a full company operating on AI.
2. **AI Employee OS** — a runtime for individual AI workers with memory, tools, and supervision.
3. **Autonomous Startup / Business Engine** — continuously drives a business mission end to end.

> **Status: Phase 7 (AI Employee OS).** Phase 0 gave us a clean, runnable foundation. Phase 1 ships the **Agent Runtime** with typed execution. Phase 2 adds the **Tool & Action System**: a permission-gated tool registry, four built-in tools, a tool-calling loop in the runtime, persistence of every tool invocation, and a Tools page in the UI. Phase 3 adds **Workflow Orchestration**: multi-step workflows (agent tasks, tool actions, conditions, delays) with structured data flow, condition branching, retry/timeout, schedule/event/webhook triggers, and a DB-backed worker + scheduler that survives restarts. Phase 4 adds the **Memory System**: persistent, provider-independent agent memory — 5 memory types, namespace isolation, hybrid retrieval (semantic + keyword + recency + importance), auto-extraction from completed executions, and injection of relevant memories into the agent's context. Phase 5 adds **Multi-Agent Orchestration**: multiple specialized agents coordinate on a shared objective — a deterministic planner decomposes the goal into tasks, a capability-based selector assembles a team, an orchestrator runs them in parallel + dependency order over an authorized message bus, and a synthesizer aggregates everything with conflict detection and source attribution. Phase 6 adds **Verification, Recovery & Evaluation**: a shared verification layer determines correctness, a bounded self-healing recovery engine fixes safe failures and escalates the rest, and an evaluation framework measures performance. Phase 7 adds **AI Employee OS**: persistent AI employees with identity, skills, goals, workload management, assignment engine, performance tracking, templates, and audit logging — transforming NEXUS into an AI workforce platform.

---

## Phase 1 — Agent Runtime

The core loop is **User → API → Agent → Task → Agent Runtime → Model Provider → Agent Result → Execution Record**.

```
┌────┐   ┌──────────┐   ┌───────┐   ┌─────────┐   ┌───────────────┐
│ UI │──▶│ API      │──▶│ Agent │──▶│ Task    │──▶│ Agent Runtime │──▶ Model Provider
└────┘   │ /agents  │   │       │   │ /tasks  │   │  (validate →  │
         │ /tasks   │   └───────┘   └─────────┘   │   build ctx →  │
         │ /execute │                              │   execute →    │──▶ AgentResult
         └──────────┘                              │   parse →      │        │
                                                   │   persist)     │        ▼
                                                   └───────────────┘   Execution Record
                                                                       (DB)
```

- **Agents** carry a role, system prompt, and model configuration (provider, model, temperature, max_tokens). Only `active` agents can execute tasks.
- **Tasks** are discrete units of work with an optional JSON input payload, assigned to a single agent.
- **Executing a task** runs the runtime pipeline, calls the configured provider, parses the structured `AgentResult`, and persists it as an `AgentExecution` with token usage, cost estimate, and latency.
- **Mock provider** (`provider = "mock"`) returns deterministic output with no API key, so the whole flow is exercisable locally and in CI.

### Try it in 60 seconds

```bash
# 1. Start the stack (or your existing local dev servers)
docker compose up -d

# 2. Create an active mock agent
curl -X POST localhost:8000/api/v1/agents -H 'Content-Type: application/json' \
  -d '{"name":"analyst","role":"analyst","status":"active","provider":"mock","model_name":"mock-model"}'

# 3. Create + assign + execute a task
TASK=$(curl -X POST localhost:8000/api/v1/tasks -H 'Content-Type: application/json' \
  -d '{"title":"Summarize Q1","input_data":{"quarter":"Q1"}}' | jq -r .id)
curl -X POST localhost:8000/api/v1/tasks/$TASK/assign -H 'Content-Type: application/json' \
  -d '{"agent_id":"<agent_id>"}'
curl -X POST localhost:8000/api/v1/tasks/$TASK/execute

# 4. Watch the activity feed
curl localhost:8000/api/v1/executions
```

The equivalent, nicer flow lives in the UI: **Agents** (create/activate/delete), **Tasks** (create/assign/execute/view executions), and **Activity** (global execution feed). Agent and task counts are surfaced on the dashboard.

---

## Phase 2 — Tool & Action System

The runtime now runs a **tool-calling loop**: after the model generates, if its JSON contains `{"tool_calls": [...]}` the runtime executes each tool through the permission-gated `ToolExecutor`, feeds the results back, and loops — until the model returns a final `AgentResult` or `max_tool_iterations` is reached.

**Registered tools** (`GET /api/v1/tools`): `calculator`, `datetime`, `text_utils`, `json_utils`.

**Permission model:** non-dangerous tools are allowed by default; `dangerous` tools require an explicit allowlist; explicit deny always wins; an admin flag bypasses all checks.

Every tool invocation is validated, authorized, timed-out (per-tool, thread-pool), and persisted as a `ToolCallRecord` in the `tool_calls` table — traceable to its execution, with arguments, result, and latency. Per-agent access is recorded in `agent_tool_permissions`.

**Driving a real tool call locally (mock):** the runtime reads optional `model_params` on a mock agent — `script` (an ordered list of JSON responses) or `reply` (a single response) — and builds a scripted `MockProvider` from them. Passing `{"script": ["{\"tool_calls\":[...]}", "{\"summary\":...}"]}` makes the mock request a tool on its first call and return a final `AgentResult` after, so the full loop (request → execute → feed back → answer) runs end-to-end over the HTTP API with no provider injection and no API key.

The **Tools** page in the UI lists every registered tool definition. The **Tasks** page embeds a per-execution tool-call inspector (`ToolCallsSection`) that fetches `GET /api/v1/tools/calls/{execution_id}` on demand.

### Try it in 60 seconds

```bash
# 1. Create an active mock agent that requests the calculator tool, then answers
curl -X POST localhost:8000/api/v1/agents -H 'Content-Type: application/json' \
  -d '{"name":"analyst","role":"analyst","status":"active","provider":"mock","model_name":"mock-model",
       "model_params":{"script":["{\"tool_calls\":[{\"tool\":\"calculator\",\"arguments\":{\"expression\":\"6 * 7\"}}]}",
                                  "{\"summary\":\"computed\",\"output\":{\"result\":42}}"]}}'

# 2. Create + assign + execute a task (the mock drives the full tool-calling loop)
TASK=$(curl -X POST localhost:8000/api/v1/tasks -H 'Content-Type: application/json' \
  -d '{"title":"Calculate 6*7 using a tool","input_data":{}}' | jq -r .id)
curl -X POST localhost:8000/api/v1/tasks/$TASK/assign -H 'Content-Type: application/json' \
  -d '{"agent_id":"<agent_id>"}'
curl -X POST localhost:8000/api/v1/tasks/$TASK/execute

# 3. Inspect the persisted tool call for that execution
EXEC_ID=$(curl localhost:8000/api/v1/executions | jq -r '.[0].id')
curl localhost:8000/api/v1/tools/calls/$EXEC_ID
```

---

## Phase 3 — Workflow Orchestration

Workflows compose agents and tools into **durable, dependency-ordered pipelines** with structured data flow, condition branching, retry/timeout, and triggers. Execution state is a single JSON document (`input` + per-step `output`); each step's `input_mapping` pulls values from it by path, so later steps consume earlier steps' output.

**Step types**: `agent_task` (runs an agent via the runtime), `tool_action` (runs a tool via the permission-gated `ToolExecutor`), `condition` (safe branching with `eq/ne/gt/gte/lt/lte/contains/not_contains` + `and`/`or`), and `delay`. A false condition marks the step — and its dependents — `skipped` for deterministic gating. Steps carry optional `retry_policy` (gated by `idempotency`: side-effecting steps are never auto-retried) and `timeout_seconds`.

**Orchestration is durable with zero extra infrastructure**: `workflow_executions` rows act as a **DB-as-queue**; an in-process `WorkflowWorker` claims them atomically and an in-process `WorkflowScheduler` fires due `schedule`/`event`/`webhook` triggers. Both auto-start with the API when `WORKFLOW_WORKER_ENABLED=true` (off in tests) and recover stale runs on restart. Workflow statuses: `draft` → `active` → `paused`.

The **Workflows** page in the UI creates/edit workflows, manages steps and triggers, activates/pauses, and visualizes each execution as a step trace. A `/workflows/[id]` page shows the latest execution running through a step-by-step visualization.

### Try it in 60 seconds

```bash
# 1. Create an active mock agent to power the research step
curl -X POST localhost:8000/api/v1/agents -H 'Content-Type: application/json' \
  -d '{"name":"researcher","role":"researcher","status":"active","provider":"mock","model_name":"mock-model"}'

# 2. Create a workflow
WF=$(curl -X POST localhost:8000/api/v1/workflows -H 'Content-Type: application/json' \
  -d '{"name":"Daily research digest","description":"Research, gate on volume."}' | jq -r .id)

# 3. Add research → condition → notify steps (dependency-ordered)
curl -X POST localhost:8000/api/v1/workflows/$WF/steps -H 'Content-Type: application/json' \
  -d "{\"name\":\"research\",\"step_type\":\"agent_task\",\"configuration\":{\"agent_id\":\"<agent_id>\",\"input_mapping\":{\"topic\":\"input.topic\"}}}"
curl -X POST localhost:8000/api/v1/workflows/$WF/steps -H 'Content-Type: application/json' \
  -d '{"name":"gate","step_type":"condition","dependencies":["research"],\
       "configuration":{"condition":{"field":"steps.research.output.lead_count","op":"gt","value":50}}}'
curl -X POST localhost:8000/api/v1/workflows/$WF/steps -H 'Content-Type: application/json' \
  -d '{"name":"notify","step_type":"tool_action","dependencies":["gate"],\
       "configuration":{"tool_name":"calculator","arguments":{"expression":"40 + 2"}}}'

# 4. Activate, execute with input, and inspect the step trace
curl -X POST localhost:8000/api/v1/workflows/$WF/activate
curl -X POST localhost:8000/api/v1/workflows/$WF/execute -H 'Content-Type: application/json' \
  -d '{"input_data":{"topic":"AI trends"}}'
EXEC_ID=$(curl localhost:8000/api/v1/workflows/$WF/executions | jq -r '.[0].id')
curl localhost:8000/api/v1/workflows/executions/$EXEC_ID/steps
```

If the mock returns `lead_count > 50`, `notify` runs; otherwise `gate` and `notify` are skipped — deterministic branching, visible in the step trace.

See [docs/workflows.md](docs/workflows.md) for the full workflow reference.

---

## Phase 4 — Memory System

NEXUS agents now have a **persistent memory**. When an agent completes a task, the runtime auto-extracts memories; on the next run, relevant ones are retrieved and injected into the agent's context — so agents recall prior work across sessions.

**Five memory types** (`working`, `episodic`, `semantic`, `procedural`, `structured`) live in a single `memories` table, isolated by **namespace** and scoped by **ownership** (agent or system). Working memory expires via TTL; every memory can be active, archived, or expired.

**Retrieval is hybrid** — `HybridRetriever` scores memories by weighted **semantic** (embedding cosine, when a provider is present) + **keyword** (Dice overlap) + **recency** (half-life decay) + **importance** + **confidence**, and exposes a per-result `breakdown` so you can see *why* something ranked. Embeddings are provider-independent: the bundled `MockEmbeddingProvider` is deterministic and free (works in CI), and `OpenAIEmbeddingProvider` is scaffolded for later. With no provider configured, retrieval still works via keyword matching.

**The runtime integrates memory into the loop**: it retrieves relevant memories *before* building the context (injecting a `[Memory]`-labeled section into the system prompt) and extracts+persists new memories *after* execution completes. Both hooks are best-effort and never block a run. Access is tracked (count + timestamp) on everything actually injected.

The **Memories** page in the UI lets you browse, hybrid-search, filter by type/status/agent, create memories manually, archive/delete, clean up expired ones, and page through large stores.

### Try it in 60 seconds

```bash
# 1. Create an active mock agent, then create + assign + execute a task
curl -X POST localhost:8000/api/v1/agents -H 'Content-Type: application/json' \
  -d '{"name":"analyst","role":"analyst","status":"active","provider":"mock","model_name":"mock-model",
       "model_params":{"reply":"{\"summary\":\"Q1 done\",\"output\":{\"quarter\":\"Q1\",\"growth\":0.12}}"}'
TASK=$(curl -X POST localhost:8000/api/v1/tasks -H 'Content-Type: application/json' \
  -d '{"title":"Summarize Q1","input_data":{"quarter":"Q1"}}' | jq -r .id)
curl -X POST localhost:8000/api/v1/tasks/$TASK/assign -H 'Content-Type: application/json' \
  -d '{"agent_id":"<agent_id>"}'
curl -X POST localhost:8000/api/v1/tasks/$TASK/execute

# 2. See the auto-extracted memories for that agent (in the "default" namespace)
curl 'localhost:8000/api/v1/memories?namespace=default'

# 3. Hybrid-search them by topic
curl -X POST localhost:8000/api/v1/memories/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"Q1 growth","namespace":"default","top_k":5}'
```

With `memory_extraction_enabled=true` (the default), executing a task automatically creates an **episodic** memory, plus **semantic** (on success+output) and **procedural** (when tools were used) memories — ready to be recalled on the next run.

See [docs/memory.md](docs/memory.md) for the full memory reference.

---

## Phase 5 — Multi-Agent Orchestration

NEXUS agents now work as **teams**. Instead of one agent per task, you state an objective and the system assembles a coordinated team to achieve it — decomposed, assigned, executed, and verified together.

**The engine is deterministic and provider-independent** (`app/orchestration/`): a `DeterministicPlanner` turns an objective into a validated task graph (e.g. a market analysis decomposes into Research → Analysis → Fact-check in parallel, then Writer). A `CapabilityAgentSelector` assigns each task to the best-available active agent by **capability coverage** — role-derived and tool-permission-derived — with round-robin load spreading. An `Orchestrator` runs ready tasks in a bounded thread pool over a DB-backed, authorization-enforced **`AgentMessageBus`**, then detects conflicts and synthesizes a final result with **full source attribution** — every finding and source traced to its agent and task.

- **Lifecycle state machine** — `created → planning → planned → assigning → running → synthesizing → completed`, with legal paths to `failed` / `partially_completed` / `cancelled`; illegal transitions raise rather than drift.
- **Parallel + sequential execution** — tasks with no dependencies run concurrently; dependents run when their prerequisites complete; a failed task marks only its dependents `skipped` (independent work continues).
- **Shared context & memory** — each task receives only the facts + prior outputs relevant to it; shared facts persist to context and Phase 4 memory.
- **Observable** — every run exposes tasks, assignments, messages, results, reviews, and a timeline in the API and the UI.
- **Workflows can call orchestrations** — an orchestration is a first-class workflow step type.
- **Demo** — create four mock agents, set an objective like *"analyze the competitive market and write a report"*, and watch the research team run end to end with no API key.

### Try it in 60 seconds

```bash
# 1. Stand up four active mock agents with market-team roles
for spec in 'researcher|researcher' 'analyst|analyst' 'fact_checker|fact_checker' 'writer|writer'; do
  role=${spec#*|}; name=${spec%|*}
  curl -X POST localhost:8000/api/v1/agents -H 'Content-Type: application/json' \
    -d "{\"name\":\"$name\",\"role\":\"$role\",\"status\":\"active\",\"provider\":\"mock\",\"model_name\":\"mock-model\",\"model_params\":{\"reply\":\"{\\\"summary\\\":\\\"$name done\\\",\\\"output\\\":{\\\"key\\\":\\\"value\\\"}}\"}}"
done

# 2. Create and run an orchestration
ORCH=$(curl -X POST localhost:8000/api/v1/orchestrations -H 'Content-Type: application/json' \
  -d '{"objective":"analyze the competitive market and write a report"}' | jq -r .id)
curl -X POST localhost:8000/api/v1/orchestrations/$ORCH/execute

# 3. Inspect the team's work
curl localhost:8000/api/v1/orchestrations/$ORCH/tasks
curl localhost:8000/api/v1/orchestrations/$ORCH/timeline
curl localhost:8000/api/v1/orchestrations/$ORCH | jq .final_result
```

With a handful of active agents in place, open the **Orchestrations** page in the UI, enter an objective, and click **Create & run** to watch the execution graph and collaboration thread populate live.

See [docs/orchestration.md](docs/orchestration.md) for the full orchestration reference.

---

## Phase 6 — Verification, Recovery & Evaluation

NEXUS now knows whether work was **right** — and what to do when it wasn't. A shared verification layer determines correctness, a bounded self-healing recovery engine fixes safe failures and escalates the rest to a human, and an evaluation framework measures how the whole system performs.

- **Verification (`app/verification/`)** — one reusable service used by the agent-loop hooks, Workflow Engine, and Orchestrator. Six strategies (`deterministic`, `schema`, `rules`, `tool`, `model`, `independent_agent`) run per a `VerificationPolicy` and aggregate to a single PASS/FAIL/PARTIAL/UNCERTAIN result with score + confidence. Deterministic-first; a verifier is never the same agent that did the work.
- **Recovery (`app/recovery/`)** — `RecoveryEngine` runs a state machine (`detected → classified → planned → recovering → reverified → recovered`) across ten bounded strategies (retry, backoff, modified-input, replan, fallback agent/tool, skip, partial completion, escalate, abort). **Safety-first:** recovery never broadens permissions and idempotency-gated budgets bound every retry — never `while not success: retry()`.
- **Escalation (`/escalations` UI + API)** — anything that can't recover safely surfaces for **human approval/rejection**; an escalation can never be approved by the agent itself.
- **Evaluation (`app/evaluation/`)** — named metrics, a deterministic 8-case dataset, persisted runs, run comparison, and regression detection — all provider-independent and testable with no API key.
- **Dashboards** — **Verifications**, **Recoveries** (with a per-attempt recovery timeline), **Evaluations** (metric bars, comparison, regression), and **Escalations** (approve/reject).

### Try it in 60 seconds

```bash
# 1. Create a mock agent that answers 42
curl -X POST localhost:8000/api/v1/agents -H 'Content-Type: application/json' \
  -d '{"name":"answerer","role":"general","status":"active","provider":"mock","model_name":"mock-model","model_params":{"reply":"{\"summary\":\"ok\",\"output\":{\"answer\":42}}"}}'

# 2. Make an execution to verify & recover against
curl -X POST localhost:8000/api/v1/tasks -H 'Content-Type: application/json' \
  -d '{"title":"computational task","input_data":{"question":"meaning of life"}}' >/dev/null
TASK=$(curl localhost:8000/api/v1/tasks | jq '.[-1] | select(.title=="computational task") | .id')
EXEC=$(curl -X POST localhost:8000/api/v1/tasks/$TASK/execute | jq -r .id)

# 3. Verify the execution's output, then run an evaluation
curl -X POST localhost:8000/api/v1/verifications -H 'Content-Type: application/json' \
  -d "{\"execution_id\":\"$EXEC\"}"
curl -X POST localhost:8000/api/v1/evaluations/runs -H 'Content-Type: application/json' \
  -d '{"use_default_dataset":true}'
curl localhost:8000/api/v1/evaluations/runs | jq .runs[0]
```

Open the **Verifications**, **Recoveries**, **Evaluations**, and **Escalations** pages in the UI to inspect runs, failure timelines, and pending human reviews.

See [docs/reliability.md](docs/reliability.md) for the full reliability reference.

---

## Phase 7 — AI Employee OS

NEXUS now has a **workforce**. AI Employees are persistent entities with organizational identity, skills, goals, policies, budgets, and performance tracking — wrapping existing agents with a management layer that makes them feel like real team members.

**The Employee OS layer** sits on top of the existing Agent Runtime, Workflow Engine, Memory, and Orchestration. It does NOT replace any Phase 1–6 code.

- **Employee lifecycle** — `draft → active → busy/paused/suspended/terminated`; every transition is validated and audit-logged. TERMINATED is final.
- **Skills** — `SkillAssessor` with adaptive proficiency learning (faster growth at low proficiency, slower as mastery increases), confidence tracking, and evidence-based updates.
- **Goals** — `GoalTracker` with `not_started → active → completed/failed/cancelled` transitions, progress tracking, priority ordering, and overall-progress aggregation.
- **Assignment engine** — weighted scoring (40% skill match, 30% workload availability, 20% role match, 10% real performance success rate) with auto-assign and specific-assign modes, plus explainable reasoning. Every successful assignment persists a real `Task` (owned by the employee's backing agent, status `queued`) and returns its `task_id`.
- **Real task inbox** — each employee has a backing agent and owns concrete `Task`s, listed via `GET /employees/{id}/tasks` and executed via `POST /employees/{id}/tasks/{id}/execute`, which feeds the outcome back into performance.
- **Workload** — `/employees/{id}/workload` counts real `Task` rows by status (queued/in-progress/completed/failed), not hardcoded zeroes.
- **Performance tracking** — running averages for tasks completed, success rate, verification pass rate, quality, latency, cost, tokens, utilization, and deadline adherence, updated in real time as assigned tasks execute. Automated reviews with strengths, weaknesses, and recommendations.
- **Context builder** — priority-ordered context sections (identity, responsibilities, goals, skills, tools, policies) with token-budget truncation, integrated with Phase 4 memory via namespace isolation.
- **Templates** — reusable employee configs; `create_from_template()` clones role, skills, tools, and policies but NOT memories, credentials, or history.
- **Audit logging** — append-only trail for every significant operation, with timeline views and workforce overview.
- **Workflow integration** — `EMPLOYEE_TASK` step type lets workflows assign tasks to employees with full context.
- **Dashboard** — Employee Directory, Employee Detail (5 tabs), Workbench, Goals Dashboard, Performance Dashboard.

### Try it in 60 seconds

```bash
# 1. Create an active employee
curl -X POST localhost:8000/api/v1/employees -H 'Content-Type: application/json' \
  -d '{"name":"research-analyst","display_name":"Alex","role":"analyst","status":"active",
       "skills":[{"name":"research","category":"core","proficiency":0.8}],
       "responsibilities":["Analyze data","Write reports"]}'

# 2. Set a goal
EMP_ID=$(curl localhost:8000/api/v1/employees | jq -r '.items[0].id')
curl -X POST localhost:8000/api/v1/employees/$EMP_ID/goals -H 'Content-Type: application/json' \
  -d '{"title":"Improve response quality","priority":1,"target":"95% quality"}'

# 3. Check workload and performance
curl localhost:8000/api/v1/employees/$EMP_ID/workload
curl localhost:8000/api/v1/employees/$EMP_ID/performance

# 4. Activate lifecycle
curl -X POST localhost:8000/api/v1/employees/$EMP_ID/activate
curl localhost:8000/api/v1/employees/workforce
```

Open the **Employees**, **Workbench**, **Goals**, and **Performance** pages in the UI to manage your AI workforce.

See [docs/employee-os.md](docs/employee-os.md) for the full Employee OS reference.

---

## Quick Start

The fastest way to see the whole stack running is Docker Compose:

```bash
# 1. Create your environment file
cp .env.example .env

# 2. Build and start everything (Postgres, Redis, API, Web)
docker compose up --build
```

Then open:

- Frontend dashboard: <http://localhost:3000>
- API docs (Swagger): <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/v1/health>

### Applying database migrations

Migrations run separately from the app so schema concerns stay distinct from the runtime. With Postgres up:

```bash
cd apps/api
source .venv/bin/activate
alembic upgrade head
```

---

## Local Development (without Docker for the app)

Run Postgres and Redis in Docker, and the app servers directly on the host:

```bash
# One-shot bootstrap (recommended)
./scripts/setup.sh
```

Or, step by step:

```bash
# Backend
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload          # http://localhost:8000

# Frontend (in a second terminal)
cd apps/web
npm install
npm run dev                            # http://localhost:3000

# Infrastructure (Postgres + Redis)
cd <repo root>
docker compose up -d postgres redis
```

---

## Running Tests & Checks

```bash
# Backend tests
cd apps/api && source .venv/bin/activate
pytest -v

# Backend lint + format
ruff check app tests
ruff format --check app tests

# Frontend lint + typecheck + build + tests
cd apps/web
npm run lint
npx tsc --noEmit
npm run build
npm run test -- --run
```

---

## Project Structure

```
nexus-ai/
├── apps/
│   ├── api/        # FastAPI backend (Python)
│   │   ├── app/
│   │   │   ├── core/       # config, logging, errors, redis
│   │   │   ├── api/v1/     # versioned HTTP endpoints
│   │   │   ├── ai/         # provider-agnostic model abstraction (incl. mock)
│   │   │   ├── db/models/  # SQLAlchemy models: agents, tasks, tools, workflows, memories, orchestrations, reliability, employees
│   │   │   ├── schemas/    # Pydantic request/response contracts
│   │   │   ├── services/   # persistence + runtime assembly (CRUD)
│   │   │   ├── verification/ # Phase 6: 6 strategies + policy + service
│   │   │   ├── recovery/   # Phase 6: diagnosis, planner, engine, state machine, escalation
│   │   │   ├── evaluation/ # Phase 6: metrics, dataset, runner, comparison, regression
│   │   │   ├── memory/     # embedding, retrieval, policies, extraction
│   │   │   ├── orchestration/ # multi-agent engine: planner, selector, orchestrator, bus, synthesizer
│   │   │   ├── runtime/    # Agent Runtime + context builder
│   │   │   ├── employee/   # AI Employee OS: lifecycle, skills, goals, workload, assignment, performance
│   │   │   ├── tools/      # tool registry, executor, permissions, built-ins
│   │   │   └── workflow/   # engine, conditions, validator, worker, scheduler
│   │   ├── alembic/        # database migrations
│   │   └── tests/          # unit, integration, and E2E tests (SQLite)
│   └── web/        # Next.js frontend (TypeScript, Tailwind)
│       ├── src/app/        # App Router pages + layout + API proxy
│       ├── src/components/ # sidebar, header, dashboard, status badges
│       └── src/lib/        # API client, shared types, nav config
├── docs/           # architecture, roadmap
├── infrastructure/
│   └── docker/     # Dockerfiles for api and web
├── scripts/        # developer tooling (setup.sh)
├── docker-compose.yml
└── .env.example    # documented environment variables
```

---

## Environment Variables

All configuration flows through environment variables — **no secrets or hardcoded values** are committed. Copy `.env.example` to `.env` and adjust. Key variables:

| Variable                | Description                          | Default (dev)                         |
| ----------------------- | ------------------------------------ | ------------------------------------- |
| `ENVIRONMENT`           | `development` / `test` / `production` | `development`                         |
| `LOG_LEVEL`             | Application log level                | `INFO`                                |
| `DATABASE_URL`          | SQLAlchemy Postgres connection URL   | `postgresql+psycopg://...@localhost:5433/nexus` |
| `POSTGRES_USER`         | Postgres user                        | `nexus`                               |
| `POSTGRES_PASSWORD`     | Postgres password                    | `nexus_dev`                           |
| `POSTGRES_DB`           | Postgres database name               | `nexus`                               |
| `REDIS_URL`             | Redis connection URL                 | `redis://localhost:6379/0`            |
| `API_HOST` / `API_PORT` | API bind address and port            | `0.0.0.0` / `8000`                    |
| `CORS_ORIGINS`          | Allowed browser origins              | `["http://localhost:3000"]`           |
| `API_BASE_URL`          | Frontend→backend proxy target        | `http://localhost:8000`               |
| `WORKFLOW_WORKER_ENABLED` | Auto-start the workflow worker + scheduler in the API | `false` |
| `WORKFLOW_EXECUTE_SYNC`   | Run `POST /workflows/{id}/execute` inline (used by tests) | `false` |
| `MEMORY_EMBEDDING_PROVIDER` | Embedding provider for semantic retrieval (`mock`/`openai`/unset) | *(unset)* |
| `MEMORY_RETRIEVAL_CONTEXT_BUDGET` | Max chars of memory content injected into context | `5000` |
| `MEMORY_RETRIEVAL_RELEVANCE_THRESHOLD` | Minimum hybrid score for a memory to be retrieved | `0.3` |
| `MEMORY_WRITE_MIN_IMPORTANCE` | Memories below this importance are not stored | `0.1` |
| `MEMORY_WRITE_DEFAULT_TTL_HOURS` | Working-memory TTL in hours | `24` |
| `MEMORY_EXTRACTION_ENABLED` | Auto-extract memories from completed executions | `true` |
| `ORCHESTRATION_EXECUTE_SYNC` | Run `POST /orchestrations/{id}/execute` inline (used by tests) | `false` |
| `ORCHESTRATION_MAX_TASKS` | Max decomposed tasks per orchestration | `50` |
| `ORCHESTRATION_MAX_AGENTS` | Max agents participating in one orchestration | `20` |
| `ORCHESTRATION_MAX_PARALLEL_AGENTS` | Thread-pool size for parallel task execution | `5` |
| `ORCHESTRATION_MAX_EXECUTION_DURATION_SECONDS` | Wall-clock cap for an orchestration run | `3600` |
| `ORCHESTRATION_MAX_MESSAGES_PER_ORCHESTRATION` | Cap on inter-agent messages per run | `500` |
| `ORCHESTRATION_MAX_REVIEW_ITERATIONS` | Cap on review revision loops | `3` |
| `ORCHESTRATION_CONFLICT_NUMERIC_THRESHOLD` | Relative-diff that flags a numeric conflict | `0.2` |
| `ORCHESTRATION_MEMORY_NAMESPACE` | Memory namespace for orchestration context | `orchestration` |
| `VERIFICATION_ENABLED` | Run verification hooks during execution | `false` |
| `VERIFICATION_DEFAULT_POLICY` | Default verification policy (JSON) | `{}` |
| `RECOVERY_ENABLED` | Enable the recovery engine | `false` |
| `RECOVERY_EXECUTE_SYNC` | Run recovery inline (used by tests) | `false` |
| `RECOVERY_MAX_ATTEMPTS` | Bounded max recovery attempts per execution | `3` |
| `EVALUATION_REGRESSION_THRESHOLD` | Δ below which a score drop flags regression | `0.05` |
| `ESCALATION_AUTO_APPROVE` | Auto-approve escalations (never in production) | `false` |
| `EMPLOYEE_DEFAULT_CAPACITY` | Default max concurrent tasks per employee | `5` |
| `EMPLOYEE_MAX_CONCURRENT_TASKS` | System-wide max concurrent tasks per employee | `5` |
| `EMPLOYEE_BUDGET_DEFAULT_MONTHLY` | Default monthly budget per employee ($) | `50.0` |
| `EMPLOYEE_EVALUATION_ON_TASK_COMPLETE` | Auto-evaluate employee on task completion | `false` |
| `EMPLOYEE_CONTEXT_MAX_TOKENS` | Max tokens in employee context | `4000` |
| `EMPLOYEE_AUDIT_ENABLED` | Enable employee audit logging | `true` |

AI provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, …) are reserved for later phases and are not required now.

> **Important:** never commit `.env` files. They are git-ignored by default.

---

## How the Frontend Reaches the Backend

The Next.js app proxies `/api/*` to the backend through a **runtime** catch-all route (`src/app/api/[...path]/route.ts`). Each request resolves `API_BASE_URL` fresh (default `localhost:8000`), so it works in local dev and in Docker without baking env vars at build time. The browser only ever talks to its own origin, so there is no CORS friction. Set `API_BASE_URL` if the backend is not on `localhost:8000`. The one exception is the health widget on the dashboard, which still uses the `/api/v1` proxy like everything else.

---

## Documentation

- [Architecture](docs/architecture.md) — system design, components, and key decisions.
- [Workflows](docs/workflows.md) — the Phase 3 workflow orchestration reference (step types, conditions, triggers, worker/scheduler, API).
- [Memory](docs/memory.md) — the Phase 4 memory system reference (memory types, hybrid retrieval, extraction, config, API).
- [Orchestration](docs/orchestration.md) — the Phase 5 multi-agent orchestration reference (planner, selection, execution, communication bus, synthesis, review, API).
- [Reliability](docs/reliability.md) — the Phase 6 reference (verification strategies & policies, failure taxonomy, recovery engine, escalation, evaluation & regression, safety model).
- [Employee OS](docs/employee-os.md) — the Phase 7 AI Employee OS reference (lifecycle, skills, goals, assignment engine, workload, performance, templates, context, audit, API).
- [Roadmap](docs/roadmap.md) — the phased plan from foundation to autonomous business engine.

---

## Contributing

This is an active, phased build. Before contributing, read the [roadmap](docs/roadmap.md) to see which phase is current. Keep changes small, typed, and tested; follow the existing lint/format conventions (ruff for Python, ESLint + strict TypeScript for the web app).