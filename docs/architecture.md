# NEXUS — System Architecture

> **Phase 3 (Workflow Orchestration).** This document describes the current architecture (Foundation + Agent Runtime + Tool System + Workflow Orchestration) and the design decisions that will shape the system as it grows. Later phases build new components on this foundation; sections marked *future* describe intent, not existing functionality.

---

## 1. Overview

NEXUS is an **Autonomous AI Workforce & Company OS**. The eventual product lets a user state a business objective and have a coordinated system of AI agents plan, execute, verify, and report on work — using external tools, memory, and controlled data.

The engineering goal for the whole project is captured in a few principles:

- **Modularity** — agents, tools, memory, orchestration, verification, and infrastructure are independently replaceable components behind clear interfaces.
- **Provider independence** — LLM access goes *only* through an abstraction layer, never a vendor SDK directly.
- **Type safety** — strong typing across the stack.
- **Config via environment** — no secrets, credentials, or URLs hardcoded.
- **Security by default** — a clean boundary between agent reasoning, tool execution, authorization, and external side effects.
- **Observability from the start** — every future agent execution is traceable.
- **Testability** — business logic is testable without a live LLM or, in many cases, a live database.

---

## 2. High-Level System Diagram

```
                         ┌─────────────────────────────┐
        Browser          │         NEXUS Web           │
   (App Router pages) ──▶│  Next.js · React · Tailwind │
                         └──────────────┬──────────────┘
                                        │  /api/*  (runtime catch-all proxy,
                                        ▼   same-origin, API_BASE_URL per request)
                         ┌─────────────────────────────┐
                         │        NEXUS API            │
                         │  FastAPI · Pydantic ·        │
                         │  /api/v1                       │
                         │  agents · tasks · executions │
                         │  tools · workflows          │
                         └───┬───────────────┬─────────┘
                             │               │
                 ┌───────────▼───┐   ┌───────▼────────┐
                 │  PostgreSQL   │   │     Redis      │
                 │  agents        │   │  (future cache │
                 │  tasks         │   │   & queues)    │
                 │  agent_executions │               │
                 │  tool_calls      │               │
                 │  workflows/steps/triggers         │
                 │  workflow_executions/step_exections│
                 └───────────┬───┘   └────────────────┘
                             │
                 ┌───────────▼───────────────────────┐
                 │       Agent Runtime (app/runtime) │
                 │  validate → build_context →       │
                 │  tool-calling loop:               │
                 │    generate → tool_calls? →      │
                 │    ToolExecutor (validate →       │
                 │      authorize → run → persist)   │
                 │    → append results → repeat      │
                 │  → parse → persist AgentExecution │
                 └───────────┬───────────────────────┘
                             │
                 ┌───────────▼───────────────────────┐
                 │  Workflow Orchestration (app/workflow)│
                 │  engine: topo-sort steps → run →  │
                 │    persist step trace             │
                 │  worker: claims queued executions │
                 │  scheduler: fires due triggers    │
                 └────────────────────────────────────┘

        AI providers resolve through the ModelProvider abstraction + registry
        (mock, openai stub). Tools register in the tool registry and execute
        through the permission-gated ToolExecutor. Workflows orchestrate agents
        and tools into dependency-ordered pipelines, driven by the in-process
        worker + scheduler over the DB-as-queue.
```

---

## 3. Major Components & Responsibilities

### 3.1 Frontend (`apps/web`)

- Next.js (App Router), React, Tailwind CSS, TypeScript (strict).
- A dashboard **shell**: sidebar navigation (Dashboard, Missions, Agents, Tasks, Activity, Approvals, Settings, Tools) and a top header.
- A **Tools** page renders every registered tool definition (parameters, danger flag, timeout, tags), pulled live from `GET /api/v1/tools`.
- The task execution detail embeds a **tool-call inspector** (`ToolCallsSection`) that fetches `GET /api/v1/tools/calls/{execution_id}` on demand.
- Every still-unfinished area renders a clear **placeholder** — no fake AI functionality.
- The `SystemStatus` widget fetches `/api/v1/health` to show live backend/database/Redis status.
- API calls are same-origin, proxied to the backend by a runtime route handler (`app/api/[...path]/route.ts`).

### 3.2 Backend (`apps/api`)

FastAPI application with:

- **Entry point** (`app/main.py`) — app factory, lifespan hook, CORS, router mounting, exception handlers.
- **Configuration** (`app/core/config.py`) — pydantic-settings `Settings` singleton driven by environment variables and `.env`.
- **Database** (`app/db/`) — SQLAlchemy engine/session, a naming-convention declarative `Base`, and Alembic migrations. Models live in `app/db/models/`: `Agent`, `Task`, `AgentExecution`, `ToolCallRecord`, `AgentToolPermission`, and the Phase 3 workflow set (`Workflow`, `WorkflowStep`, `WorkflowTrigger`, `WorkflowExecution`, `StepExecution`).
- **Schemas** (`app/schemas/`) — Pydantic request/response contracts decoupled from the ORM, plus the `AgentResult` structured-output contract and tool/tool-call read schemas.
- **Services** (`app/services/`) — thin persistence CRUD (`AgentService`, `TaskService`, `ExecutionService`, `ToolCallService`, `PermissionService`) and a runtime-assembly dependency (`create_runtime`) that wires the runtime to a request-scoped session.
- **Tools** (`app/tools/`) — the Tool & Action system: types, registry, permission context, and executor, plus built-in tools (see §3.5).
- **Runtime** (`app/runtime/`) — the Agent Runtime orchestrator, the context builder, and the tool-calling loop (see §3.4).
- **API versioning** (`app/api/v1/`) — v1 endpoints mounted under `/api/v1` for agents, tasks (create/assign/execute), executions, and tools/tool-calls; additive versioning for the future.
- **Health endpoint** (`app/api/v1/endpoints/health.py`) — always returns 200 when reachable; individual checks degrade rather than failing the request.
- **Error handling** (`app/core/errors.py`) — typed exception hierarchy rendered as a consistent JSON envelope; no internals leaked to clients.
- **Logging** (`app/core/logging.py`) — structured, namespaced logging.
- **Redis** (`app/core/redis.py`) — lazy client; Redis absence never blocks startup. Reserved for future queues/cache.

### 3.3 AI Abstraction (`app/api/app/ai/`)

The provider-agnostic model layer:

- **`types.py`** — shared provider-agnostic payloads (`ChatMessage`, `GenerationOptions`, `ModelResponse`, `TokenUsage`).
- **`interfaces.py`** — the `ModelProvider` Protocol (`generate`, `stream`, `structured_output`). Logic depends on this interface, never a vendor SDK.
- **`base.py`** — `BaseModelProvider` with shared default-option plumbing.
- **`providers/`** — concrete adapters. Phase 0 ships a dependency-free `OpenAIProvider` stub for exercising the seam.
- **`registry.py`** — resolves provider by name (`get_provider("openai")`); the DI seam future execution code will use.

The separation the spec requires is explicit:

```
agent →  model interface  →  provider adapter  →  vendor SDK
```

Not: `agent → vendor SDK`.

`MockProvider` (`providers/mock_provider.py`) is a first-class, deterministic test double registered in the registry — executing an `active` agent with `provider="mock"` runs the full runtime loop with no API key. It supports an optional `script` (an ordered list of responses — e.g. a `tool_calls` request followed by a final `AgentResult`) or a single `reply`, so a mock agent can drive the entire tool-calling loop end-to-end over the HTTP API without provider injection.

### 3.4 Agent Runtime (`app/runtime/`)

The heart of Phase 1, extended in Phase 2 into a **tool-calling loop**. `AgentRuntime.execute_task` runs:

```
load agent → validate (assigned, active, provider+model) → begin execution (DB)
  → build_context (system = role + system prompt + tool definitions;
                   user = title + description + input JSON)
  → repeat (up to max_tool_iterations):
       provider.generate → if tool_calls: execute via ToolExecutor
         (validate → authorize → run → persist) → append results to context
       until model returns a final AgentResult
  → parse AgentResult → complete execution (DB)
```

- **`context.py`** builds the `ChatMessage` list and a JSON-based, provider-agnostic tool-calling protocol: when tools are enabled, the system prompt includes formatted tool definitions and the user message tells the model how to request a tool (returning `{"tool_calls": [...]}`). `append_tool_results()` feeds each tool result back as an assistant + user message pair. `agent_is_executable` gates on `status == active`.
- **`runtime.py`** orchestrates services and the resolved `ModelProvider`. On each iteration it inspects the model's JSON for a `tool_calls` array; if present, it executes each call via `ToolExecutor` and loops. It stops when the model returns a final `AgentResult`, when it exceeds `max_tool_iterations` (→ `FAILED`), or when tools are disabled (`enable_tools=False` reproduces Phase 1 behavior). Token usage accumulates across iterations. On parse/model failure it persists a `FAILED` execution and marks the task `failed`, so nothing is lost. Successful runs store `AgentResult.output_data`, token usage, a per-provider cost estimate, and `latency_ms`. A provider may be injected (tests) or resolved per-execution from the agent's `provider` field via the registry.
- Every run is persisted as an **`AgentExecution`** — typed, traced, reproducible — with each tool invocation recorded as a **`ToolCallRecord`**.

### 3.5 Tool & Action System (`app/tools/`)

The Phase 2 capability boundary between agent **reasoning** and tool **side effects**.

- **`types.py`** — shared tool contracts: `ToolDefinition` (name, description, parameters, `dangerous` flag, timeout, tags), `ToolParameter` (name/type/required/default/enum), and `ToolResult` (status: success/error/timeout/denied; data, error, execution time).
- **`base.py`** — `BaseTool` ABC: `definition`, `execute(**kwargs)`, and `validate_arguments()` which coerces types and enforces required/enum constraints.
- **`registry.py`** — module-level registry with auto-registration of built-ins; `register_tool`/`get_tool`/`unregister_tool`/`get_tool_definitions`/`list_tool_names`/`tool_exists`.
- **`permissions.py`** — `PermissionContext` (agent id, allowed/denied tool sets, admin flag) and `check_permission()`: admin bypass → explicit deny → allowlist check → dangerous-guard → allowed. Sensitive (`dangerous`) tools require an explicit allowlist; non-dangerous tools are allowed by default.
- **`executor.py`** — `ToolExecutor` is the single entry point. Flow: resolve from registry → validate arguments → check permissions → execute with a per-tool timeout on a shared thread pool → persist to `tool_calls`. A resolution/validation failure or permission denial is returned as an `ERROR`/`DENIED` `ToolResult` (not raised), so the runtime can keep looping.
- **`builtin/`** — `calculator` (safe expression evaluator), `datetime` (now/format/diff), `text_utils` (case/count/trim/replace/reverse/words), `json_utils` (parse/validate/pretty/minify/query/keys).
- **Persistence** — `tool_calls` (execution id, tool name, arguments JSON, result status/data/error, execution time, iteration) and `agent_tool_permissions` (per-agent granted/denied). Permissions are loaded per-execution by `PermissionService.get_context()`.

### 3.6 Workflow Orchestration (`app/workflow/`)

The Phase 3 coordination layer that composes agents and tools into durable, dependency-ordered pipelines.

- **`engine.py`** — `WorkflowEngine`: loads a `WorkflowExecution` + its steps, topologically sorts them by dependencies, and runs each step in order, resolving input mappings from a shared execution-state document and persisting a per-step trace (`StepExecution`). `_run_step` dispatches by step type: `agent_task` → `AgentRuntime`, `tool_action` → `ToolExecutor`, `condition` → the safe condition evaluator, `delay` → a cancellable sleep. A failed condition marks the step (and its dependents) `skipped`. Denied/unresolvable tool steps fail the workflow. Retries honor `retry_policy` + `idempotency`; per-step `timeout_seconds` marks an over-long step `timed_out`.
- **`conditions.py`** — a **safe** condition interpreter (ops `eq/ne/gt/gte/lt/lte/contains/not_contains`, nested `and`/`or`) over JSON paths — no `eval()`, no arbitrary code.
- **`mapping.py`** / **`state.py`** — `resolve_mapping(mapping, state)` pulls step inputs from `{"input": …, "steps": {name: {output, status}}}`; `WorkflowState` wraps the same document for path reads and step-output writes.
- **`validator.py`** — `validate_workflow_steps()` checks unique names, dependency existence, cycle-freedom (DFS), valid agent/tool refs, valid configs, timeout > 0, and retry-policy safety (no auto-retry on `non_idempotent`/`side_effecting`).
- **`queue.py`** / **`worker.py`** — the **DB-as-queue**: `workflow_executions` rows in `queued` state are claimed atomically by `WorkflowWorker` (`FOR UPDATE SKIP LOCKED` on Postgres, `SELECT + UPDATE` on SQLite), marked `running`, and run via the engine. `recover_stale()` marks executions stuck `running` past the timeout as `timed_out`, so a restart never leaves ghost work.
- **`scheduler.py`** — `WorkflowScheduler` polls enabled triggers on `active` workflows whose `next_run_at` has arrived, creates a `queued` execution per firing, and advances `next_run_at` (cron via `croniter`, or fixed interval).
- **`app/services/workflow_service.py`** — `WorkflowService`: workflow CRUD + lifecycle (validate→activate→pause), step/trigger management, execution creation/listing/cancel, and the step-trace read — with `to_dict`/`step_to_dict`/`trigger_to_dict`/`execution_to_dict`/`step_execution_to_dict` serializers.
- **Endpoints** (`app/api/v1/endpoints/workflows.py`) — full workflow API under `/api/v1/workflows`: CRUD, activate/pause, validate, steps, triggers, execute, and executions (with per-execution step traces and cancel). Manual execute runs inline when `workflow_execute_sync` is set (test suite) and otherwise enqueues for the worker.

The worker and scheduler are **in-process daemon threads** started in the FastAPI lifespan when `workflow_worker_enabled` is true — durable, restart-safe orchestration with zero extra runtime infrastructure (no Redis).

### 3.7 Infrastructure & Database

- **Docker Compose** (root) — `postgres`, `redis`, `api`, `web` services with healthchecks and dependency ordering.
- **PostgreSQL 16** — primary store, accessed via SQLAlchemy; migrations via Alembic.
- **Redis 7** — reserved for future caching/task infrastructure; wired but optional in Phase 0.
- **Dockerfiles** — separate images for the API (Python 3.14) and the web app (Node 24), run as non-root.

---

## 4. Communication Boundaries

- **Browser ↔ Web:** React client components over the Next.js App Router; server components render statically where possible.
- **Web ↔ API:** the web app proxies `/api/*` to the backend. Business effects happen in the *API*, not in the browser.
- **API ↔ Database:** via SQLAlchemy ORM through the DI-provided session. Domain logic never touches the DB driver directly.
- **API ↔ Redis:** via a lazy client; degradation is reported, never fatal.
- **API ↔ AI providers:** always through the `ModelProvider` abstraction and registry. No endpoint depends on a concrete provider.
- **Runtime ↔ Tools:** the runtime calls `ToolExecutor.execute(...)` (never a tool directly); the executor enforces validation, authorization, timeout, and persistence before returning a `ToolResult`. Tools never have direct access to the database or model context — only to the arguments the runtime passes.

---

## 5. Key Design Decisions

| Area | Decision | Why |
| ---- | -------- | --- |
| Monorepo layout | `apps/{api,web}` + `docs/`, `infrastructure/`, `scripts/` | Separate dependency graphs (Python vs Node); the spec's `services/`, `packages/`, `tests/` dirs are intentionally omitted until they hold real content. |
| Python env | stdlib `venv` + pip, `requirements*.txt` | No `uv`/pipenv installed; zero new tooling. `uv` is a recommended future upgrade. |
| Pins | `>=` minimum versions during Python 3.14 bootstrap | Python 3.14 is bleeding-edge; only newest releases ship cp314 wheels. Pin exact versions (or switch to `uv` + a lockfile) once the toolchain settles. |
| DB driver | `psycopg[binary]` v3 (sync) | Broad wheel availability on Python 3.14. Async (`asyncpg`) can be introduced when async DB I/O is warranted. |
| API versioning | single `api_v1_prefix` constant; additive routers | v2 is a new router, not a fork of existing code. |
| Health semantics | 200 even when a dependency is degraded | Operators distinguish "API down" from "dependency down"; the checks field carries detail. |
| Redis | lazy + optional | Keeps the core API bootable; health reports Redis state. |
| Web→API | same-origin runtime proxy | Avoids CORS entirely in dev and Docker. Env vars resolved per-request, not at build time. |
| Observability | `ModelResponse` carries `latency_ms`, `usage`, timestamps; every run persisted as an `AgentExecution` | Each execution is typed, traced, and reproducible. |
| Runtime pipeline | `validate → build_context → execute → parse → persist` in `app/runtime/` | A single deterministic path for one agent + one task + one model + reliable persistence. |
| Structured output | `AgentResult` is the contract between model and business layer | Callers trust the schema, not free-form model JSON; parse failures are surfaced and persisted. |
| Provider injection | Runtime accepts an injected provider or resolves via the registry from `agent.provider` | Tests override the provider (MockProvider) without touching production wiring. |
| Testability | Services/runtime tested on in-memory SQLite (`StaticPool`); API via dependency overrides | The full loop runs in CI without Docker or an API key. |
| Security | non-root Docker users; secrets strictly in env; no `.env` committed | Least-privilege and no-secret-commit from day one. |
| Tool signature | `BaseTool.execute(**kwargs)` taking validated keyword args | Keeps execution uniform across tools and lets `validate_arguments` coerce types before dispatch. |
| Tool permissions | `PermissionContext`: admin bypass → explicit deny → allowlist → dangerous-guard → allowed | Sensitive tools are opt-in; non-dangerous tools flow by default; deny always wins. Explicit deny beats allowlist so an operator can hard-block a tool. |
| Failure handling | Executor returns an `ERROR`/`DENIED` `ToolResult` instead of raising | The tool-calling loop can observe the failure, feed it back to the model, and continue. |
| Tool-calling protocol | JSON-shaped tool requests inside message content (`{"tool_calls": [...]}`) with results appended as assistant/user pairs | Provider-agnostic — works with the mock and any provider without tight coupling to a vendor's native tool-call schema. |
| Tool timeouts | Per-tool `timeout_seconds` enforced via a shared `ThreadPoolExecutor` | A misbehaving tool cannot hang the model loop indefinitely. |
| Bool defaults in Alembic | `server_default=sa.true()` for boolean columns | `1` is not valid PostgreSQL boolean SQL; `sa.true()` ports across PostgreSQL and SQLite. |

---

## 6. Data Model (Phase 3)

Phase 0 created a minimal `agents` stub. Phase 1 expanded it and added the runtime tables; Phase 2 added the tool tables; Phase 3 adds the workflow tables:

- **`agents`** — id, name (unique), role, description, `status` (draft/active/inactive), `system_prompt`, and model config (`provider`, `model_name`, `temperature`, `max_tokens`, `model_params` JSON). Only `active` agents execute tasks.
- **`tasks`** — id, title, description, `input_data` (JSON payload for the agent), `status` (pending/queued/in_progress/completed/failed/cancelled), `assigned_agent_id` FK → agents, and timestamps including `executed_at`.
- **`agent_executions`** — id, `task_id` + `agent_id`, `status` (running/succeeded/failed/cancelled), `input_data`/`output_data`/`error`, the resolved `provider` + `model_name`, token usage (`prompt/completion/total`), `estimated_cost`, `latency_ms`, and timestamps. This is the auditable record of "what actually happened."
- **`tool_calls`** — id, `execution_id` (indexed FK → agent_executions), `tool_name`, `arguments` JSON, `result_status` (success/error/timeout/denied), `result_data`/`result_error` JSON, `execution_time_ms`, `iteration`, `created_at`. One row per tool invocation within an execution, so the runtime's tool activity is fully traceable.
- **`agent_tool_permissions`** — id, `agent_id` (indexed), `tool_name`, `granted` boolean (default `true`), `created_at`. An empty set allows all non-dangerous tools; populated rows restrict/deny; a `granted=false` row hard-denies a tool.
- **`workflows`** — id, `name` (unique), `description`, `status` (draft/active/paused/archived), `version`, `configuration` JSON, and timestamps. The durable definition of a pipeline.
- **`workflow_steps`** — id, `workflow_id` FK → workflows, `name` (unique within a workflow), `step_type` (agent_task/tool_action/condition/delay), `configuration` JSON (agent_id + input mapping, tool_name + arguments, condition, or duration), `order`, `dependencies` JSON (list of step names), `timeout_seconds`, `retry_policy` JSON, `idempotency` tag. Indexed on `(workflow_id, name)`.
- **`workflow_triggers`** — id, `workflow_id` FK, `trigger_type` (schedule/event/webhook), `configuration` JSON (`cron`/`interval`/`event_name`/`webhook_secret`), `enabled` boolean, `next_run_at`. Indexed on `(next_run_at, enabled)` for the scheduler poll.
- **`workflow_executions`** — id, `workflow_id` FK, `status` (queued/running/completed/failed/cancelled/timed_out), `trigger_type`, `input_data`/`output_data`/`error` JSON, `started_at`, `completed_at`, `duration_ms`. Indexed on `status` for the worker claim query — the **DB queue**.
- **`step_executions`** — id, `workflow_execution_id` FK, `workflow_step_id` FK, `status` (pending/ready/running/completed/failed/skipped/cancelled/timed_out), `input_data`/`output_data`/`error` JSON, `attempt_number`, `started_at`, `completed_at`, `duration_ms`. One row per step per execution — the auditable step trace.

Enums are stored as plain VARCHAR values (e.g. `active`, `completed`, `running`) via the ORM (`native_enum=False`, `values_callable`) so the DB columns match the migration's `String` columns and stay portable across PostgreSQL and the SQLite test DB. Boolean server defaults use `sa.true()` for PostgreSQL compatibility.

Planned for later phases (not yet created): `users`, `organizations`, `missions`, `memories`, `approvals`, `evaluations`.

These arrive incrementally; none are created prematurely.

---

## 7. Capability Accommodation Matrix

The 22 architecture requirement areas drive NEXUS's long-term design. Each is designed in Phase 0 to be implementable without rewrites; none are built prematurely. This matrix shows how each capability is architecturally accommodated from day one.

### 7.1 Automation & Workflow Engine

- **Phase:** 3 (Workflow Orchestration) — *built*
- **Design accommodation:** `app/workflow/` implements a durable orchestration layer: a dependency-aware `WorkflowEngine`, a safe condition evaluator, per-step retry/timeout/idempotency, triggers (schedule/event/webhook), and a **DB-as-queue** worker + scheduler that survive restarts (no Redis at runtime).
- **Interface points:** `WorkflowEngine.execute()`, `WorkflowQueue.claim_next()`, `WorkflowWorker`/`WorkflowScheduler`, `validate_workflow_steps()`, and the `/api/v1/workflows*` endpoints. The queue is `workflow_executions` rows (status `queued` → worker claims with `FOR UPDATE SKIP LOCKED`); a Postgres-advisory-lock or Redis-backed queue can replace it later without changing callers.

### 7.2 Mission System

- **Phase:** 1 (Agent Runtime)
- **Design accommodation:** The `missions` table design placeholder exists in the data model (Section 6). The `agents` stub table proves the ORM + Alembic pipeline that `missions` will follow. CRUD endpoint pattern established by the health endpoint structure.
- **Interface points:** `Mission` model, `MissionService`, `POST /api/v1/missions`, `GET /api/v1/missions/{id}`.

### 7.3 Agent Runtime

- **Phase:** 1 (Agent Runtime) — *built*
- **Design accommodation:** `app/runtime/` implements a single deterministic execution pipeline (`validate → build_context → execute → parse → persist`) consuming a resolved `ModelProvider`. `AgentExecution` records token usage, cost, latency, and errors, so every run is typed and traced. The `MockProvider` is registered in the registry for keyless local/CI execution.
- **Interface points:** `AgentRuntime.execute_task()`, `build_context()`, the `ModelProvider` Protocol + registry, and the `AgentResult` schema. A reasoning *loop* (multi-step `generate → act → repeat` with tools) is future work (Phase 2+); Phase 1 executes a single task end-to-end.

### 7.4 Multi-Agent Communication

- **Phase:** 4 (Multi-Agent Orchestration)
- **Design accommodation:** Redis pub/sub or a dedicated message bus. The existing `get_redis_client()` in `app/core/redis.py` establishes the connection pattern. Agent-to-agent messages will use an event schema with `execution_id` propagation.
- **Interface points:** `EventBus.publish()`, `EventBus.subscribe()`. Events carry `execution_id` for tracing.

### 7.5 Tool & Action System

- **Phase:** 2 (Tool System) — *built*
- **Design accommodation:** `app/tools/` implements a registry (`register`/`get`/`unregister`/`list`), a permission-gated `ToolExecutor`, and built-in tools. Each tool is a typed, sandboxed capability (argument validation → authorization → timeout → persistence). The runtime's tool-calling loop drives them.
- **Interface points:** `get_tool(name)`, `register_tool(tool)`, `ToolExecutor.execute(...)`, `check_permission(...)`, `BaseTool.definition`/`execute`. The executor returns structured `ToolResult`s so the loop can continue past failures; a reasoning loop over arbitrary vendor-native tool schemas is future work.

### 7.6 Browser Automation & Computer Use

- **Phase:** 3 (Memory) or later
- **Design accommodation:** Sandbox execution interface for isolated container-based browser automation. The Docker architecture already supports per-service isolation.
- **Interface points:** `BrowserAction` type, `Sandbox.execute()` with timeout/resource limits.

### 7.7 Memory Architecture

- **Phase:** 3 (Memory)
- **Design accommodation:** Short-term memory (context window management) and long-term memory (vector DB or structured store). The `ModelResponse.usage` field already tracks token consumption, which drives context window decisions.
- **Interface points:** `MemoryStore.store()`, `MemoryStore.retrieve()`, `MemoryStore.search()`.

### 7.8 Verification & Self-Correction

- **Phase:** 7 (Autonomous Business Engine)
- **Design accommodation:** Verification hooks in the agent loop. After each `generate` → tool call, a verification step checks output correctness. The evaluation pipeline interface supports scoring.
- **Interface points:** `Verifier.verify()`, `CorrectionLoop.apply()`.

### 7.9 Failure Recovery & Resilience

- **Phase:** 3 (Workflow Orchestration) through 4
- **Design accommodation:** Per-step `retry_policy` with exponential/fixed backoff is built into phases 3 workflow steps, gated by idempotency (no auto-retry on side-effecting steps). The worker's `recover_stale()` marks executions stuck `running` past the timeout as `timed_out`, and a dead-letter queue + circuit breaker for external services remain future.
- **Interface points:** `retry_policy`/`timeout_seconds`/`idempotency` on steps, `WorkflowWorker.recover_stale()`, and future `DeadLetterQueue`/`CircuitBreaker`.

### 7.10 Permission & Security System

- **Phase:** 6 (AI Company)
- **Design accommodation:** RBAC model with role hierarchy. Auth middleware pattern. Policy engine for fine-grained access control. The existing `CORS_ORIGINS` config establishes the security config pattern.
- **Interface points:** `AuthService.authorize()`, `PolicyEngine.evaluate()`, `RBAC` role/permission models.

### 7.11 Human-in-the-Loop Gates

- **Phase:** 5 (AI Employee OS)
- **Design accommodation:** Approval workflow model where sensitive actions pause for human review. The `approvals` table and webhook/callback pattern for external input are planned.
- **Interface points:** `ApprovalService.request()`, `ApprovalService.approve()`, `ApprovalService.reject()`.

### 7.12 Observability & Telemetry

- **Phase:** 5 (AI Employee OS)
- **Design accommodation:** Structured logging via `app/core/logging.py` is already in place. Execution tracing will propagate `execution_id` across all operations. The `ModelResponse` already carries `latency_ms` and `usage`.
- **Interface points:** `execution_id` propagation, structured log fields, metrics export.

### 7.13 Evaluation & Benchmarking

- **Phase:** 7 (Autonomous Business Engine)
- **Design accommodation:** Evaluation harness interface for running agent/task benchmarks. Metrics collection in the agent loop captures success rates, latency, and cost.
- **Interface points:** `Evaluator.run()`, `Benchmark.suite()`, `MetricCollector`.

### 7.14 AI Employee Model

- **Phase:** 5 (AI Employee OS)
- **Design accommodation:** Employee schema (role, permissions, status, schedule) extends the existing `agents` table. Dashboard integration for live agent status.
- **Interface points:** `Employee` model, `EmployeeService`, dashboard status API.

### 7.15 AI Company Layer

- **Phase:** 6 (AI Company)
- **Design accommodation:** Organization/workspace model with multi-tenancy via `tenant_id` column. The `organizations` table and workspace settings are planned.
- **Interface points:** `Organization` model, `Workspace` model, `tenant_id` column on all domain tables.

### 7.16 Dynamic Agent Creation

- **Phase:** 1 (Agent Runtime)
- **Design accommodation:** Agent factory pattern where missions are decomposed into agent roles, and new agent instances are spawned at runtime. The `agents` table stores agent definitions.
- **Interface points:** `AgentFactory.create()`, `AgentFactory.spawn()`.

### 7.17 Resource & Budget Management

- **Phase:** 6 (AI Company)
- **Design accommodation:** Token/cost tracking in `ModelResponse.usage` is already in place. Budget limits will be enforced at the provider and mission level via config.
- **Interface points:** `BudgetManager.check()`, `BudgetManager.charge()`, `UsageTracker`.

### 7.18 Feedback Loops & Learning

- **Phase:** 7 (Autonomous Business Engine)
- **Design accommodation:** Feedback collection interface where humans or automated verifiers provide scores. The evaluation scoring pipeline processes feedback to improve future agent behavior.
- **Interface points:** `FeedbackCollector.submit()`, `ScorePipeline.process()`.

### 7.19 Simulation & Sandbox

- **Phase:** 8 (Evaluation, Security & Production Hardening)
- **Design accommodation:** Isolated execution environments using container-per-agent or container-per-task patterns. The Docker architecture supports this directly.
- **Interface points:** `Sandbox.create()`, `Sandbox.execute()`, `Sandbox.destroy()`.

### 7.20 Agent Marketplace

- **Phase:** 8 (Evaluation, Security & Production Hardening)
- **Design accommodation:** Agent template registry where pre-built agent definitions are published and subscribed. The `ModelProvider` registry pattern extends naturally to agent templates.
- **Interface points:** `AgentTemplate.register()`, `AgentTemplate.instantiate()`, `Marketplace.publish()`.

### 7.21 Closed-Loop Autonomous Business

- **Phase:** 7 (Autonomous Business Engine)
- **Design accommodation:** Long-running mission engine with goal-tracking state machine. The mission decomposition + execution loop runs continuously, verifying progress against business objectives.
- **Interface points:** `MissionEngine.run()`, `GoalTracker.progress()`, `SelfHealing.recover()`.

### 7.22 Cross-Cutting: Config, Secrets, Auth

- **Phase:** 6 (AI Company)
- **Design accommodation:** `pydantic-settings` config is already the single source of truth. Env-based secrets are the pattern (`.env` files, Docker secrets, cloud secret managers). Auth middleware will wrap FastAPI dependencies.
- **Interface points:** `Settings` singleton, `SecretsManager.get()`, `AuthMiddleware`.

---

## 8. Future Architecture (later phases)

- **Phase 1+ (Agent Runtime):** real provider adapters (OpenAI, Anthropic, Gemini, local); structured outputs.
- **Phase 2+ (Tool & Action System):** a richer tool set (web fetch/HTTP, file/shell in a sandbox, browser automation), per-agent permission management UI + endpoint, and vendor-native tool-call schema adoption for real providers.
- **Phase 3+ (Workflow Orchestration):** a visual workflow editor, venue triggers/webhook guards, and richer step types (sub-workflow, parallel fan-out — the sequential engine already returns execution state in dependency order).
- **Memory:** short-term (context/conversation) and long-term (vector/searchable) stores.
- **Multi-agent orchestration:** mission decomposition, role assignment, coordination, failover (workflows already reuse a DB-backed queue + worker with per-execution observability).
- **Approvals & RBAC:** human-in-the-loop gates for sensitive side effects.

See [roadmap.md](roadmap.md) for the full phased plan.