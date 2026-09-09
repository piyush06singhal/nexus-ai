# NEXUS

**An Autonomous AI Workforce & Company OS.**

NEXUS lets you hand a high-level business objective to a system of AI agents that plans, coordinates, and executes toward it. It combines three long-term ambitions into one platform:

1. **AI Company in a Box** — a full company operating on AI.
2. **AI Employee OS** — a runtime for individual AI workers with memory, tools, and supervision.
3. **Autonomous Startup / Business Engine** — continuously drives a business mission end to end.

> **Status: Phase 3 (Workflow Orchestration).** Phase 0 gave us a clean, runnable foundation. Phase 1 ships the **Agent Runtime** with typed execution. Phase 2 adds the **Tool & Action System**: a permission-gated tool registry, four built-in tools, a tool-calling loop in the runtime, persistence of every tool invocation, and a Tools page in the UI. Phase 3 adds **Workflow Orchestration**: multi-step workflows (agent tasks, tool actions, conditions, delays) with structured data flow between steps, condition branching, retry/timeout, schedule/event/webhook triggers, and a DB-backed worker + scheduler that survives restarts — all orchestrated durably with no Redis.

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
│   │   │   ├── db/models/  # SQLAlchemy models: agents, tasks, tools, workflows
│   │   │   ├── schemas/    # Pydantic request/response contracts
│   │   │   ├── services/   # persistence + runtime assembly (CRUD)
│   │   │   ├── runtime/    # Agent Runtime + context builder
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

AI provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, …) are reserved for later phases and are not required now.

> **Important:** never commit `.env` files. They are git-ignored by default.

---

## How the Frontend Reaches the Backend

The Next.js app proxies `/api/*` to the backend through a **runtime** catch-all route (`src/app/api/[...path]/route.ts`). Each request resolves `API_BASE_URL` fresh (default `localhost:8000`), so it works in local dev and in Docker without baking env vars at build time. The browser only ever talks to its own origin, so there is no CORS friction. Set `API_BASE_URL` if the backend is not on `localhost:8000`. The one exception is the health widget on the dashboard, which still uses the `/api/v1` proxy like everything else.

---

## Documentation

- [Architecture](docs/architecture.md) — system design, components, and key decisions.
- [Workflows](docs/workflows.md) — the Phase 3 workflow orchestration reference (step types, conditions, triggers, worker/scheduler, API).
- [Roadmap](docs/roadmap.md) — the phased plan from foundation to autonomous business engine.

---

## Contributing

This is an active, phased build. Before contributing, read the [roadmap](docs/roadmap.md) to see which phase is current. Keep changes small, typed, and tested; follow the existing lint/format conventions (ruff for Python, ESLint + strict TypeScript for the web app).