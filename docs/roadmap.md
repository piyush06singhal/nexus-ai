# NEXUS — Roadmap

The platform is built incrementally, phase by phase. Each phase ships verifiable functionality and is validated before the next begins. **Marked items in later phases are planned, not yet built. Phase 0 (Foundation), Phase 1 (Agent Runtime), Phase 2 (Tool & Action System), Phase 3 (Workflow Orchestration), Phase 4 (Memory System), and Phase 5 (Multi-Agent Orchestration) are complete.**

---

## ✅ Phase 0 — Foundation *(current)*

Set up the clean, runnable engineering foundation.

- Monorepo: `apps/api` (FastAPI) + `apps/web` (Next.js) + docs/infrastructure/scripts.
- FastAPI backend: config, health endpoint, structured errors, logging, DI structure, Redis wiring, API versioning under `/api/v1`.
- PostgreSQL + SQLAlchemy + Alembic with a minimal `agents` stub table.
- Provider-agnostic AI abstraction: `ModelProvider` interface + a dependency-free `OpenAIProvider` stub + provider registry.
- Next.js dashboard shell (sidebar, header, system status, placeholders for Missions/Agents/Tasks/Activity/Approvals/Settings).
- Docker Compose (postgres, redis, api, web), Dockerfiles, `.env.example`, docs.
- Quality gates: ruff + pytest (backend), ESLint + strict TS build (frontend).
- CI: GitHub Actions (backend tests + lint, frontend build + lint).
- Pre-commit hooks (ruff, trailing-whitespace, end-of-file-fixer).
- Frontend unit tests (vitest).
- Backend dependency lockfile (`requirements.lock`).
- OpenAPI → TypeScript codegen setup (`packages/shared`).
- Web Docker image optimized to standalone mode.

**Exit criteria:** frontend, backend, Postgres, Redis all start; frontend talks to backend; health + migrations + tests + lint/typecheck all pass; Docker Compose works; docs accurate; no secrets committed; CI and pre-commit hooks operational.

---

## ✅ Phase 1 — Agent Runtime *(current)*

- ~~Real model provider adapters behind the abstraction~~ _(reserved; the provider-agnostic seam is in place)_
- Core data models: `agents` (full), `tasks`, `agent_executions` + CRUD APIs + ORM tests.
- A basic **agent execution** (`load agent → validate → build context → execute → parse → persist`) with structured outputs validated by Pydantic.
- `MockProvider` registered in the registry so the whole loop runs deterministically without an API key.
- Frontend pages for Agents, Tasks (assign + execute + per-task executions), and a global Activity execution feed; dashboard shows live agent/task counts.
- Unit + integration + E2E tests (SQLite-backed) plus live PostgreSQL verification.

**Exit criteria (met):** an agent completes a scripted task using the mock (or real) provider with a typed, traced call path persisted to an `AgentExecution` record.

## ✅ Phase 2 — Tool System *(completed)*

- Executable **tools** as typed, sandboxed capabilities (`app/tools/`).
- Tool **registry** with auto-registration of built-ins and `register`/`get`/`unregister`/`list`/`exists` operations.
- **Argument validation** against each tool's parameter schema (type coercion, required checks, enums).
- Tool **permissions** — a `PermissionContext` gate between agent reasoning and tool side effects: non-dangerous tools allowed by default, `dangerous` tools require an explicit allowlist, explicit deny overrides, and an admin bypass.
- **`ToolExecutor`** — the single entry point: resolve → validate → authorize → execute (with per-tool timeout via a thread pool) → persist to DB.
- Four **built-in tools**: `calculator` (safe expression evaluator), `datetime` (now/format/diff), `text_utils` (case/count/trim/replace/reverse/words), and `json_utils` (parse/validate/pretty/minify/query/keys).
- Concrete **DB models + Alembic migration** (`0003`): `tool_calls` (every invocation within an execution) and `agent_tool_permissions` (per-agent access).
- **Runtime integration** — `AgentRuntime` now runs a tool-calling loop: `model.generate` → if `tool_calls` → execute via `ToolExecutor` → feed results back → repeat until a final `AgentResult`. Token usage accumulates across iterations; `max_tool_iterations` prevents runaway loops; a per-iteration `enable_tools` flag retains Phase 1 behavior.
- **API endpoints**: `GET /api/v1/tools`, `GET /api/v1/tools/{name}`, `GET /api/v1/tools/calls/{execution_id}`.
- **Frontend**: a Tools page listing every registered tool (params, danger, timeout, tags) and tool-call inspection inside the task execution detail.
- Comprehensive tests: built-in tools, registry, executor/permissions, runtime tool-calling loop, and tool API.

**Exit criteria (met):** an agent can invoke approved tools safely via the runtime loop; sensitive (`dangerous`) tools require explicit authorization; every tool call is validated, authorized, timed-out, and persisted.

## ✅ Phase 3 — Workflow Orchestration *(completed)*

- Durable **workflow engine** (`app/workflow/engine.py`) with dependency-aware, **sequential** step execution (topological sort; a step runs when all its dependencies complete). No multi-threading — fully deterministic and testable.
- Four **step types**: `agent_task` (runs an agent via `AgentRuntime`), `tool_action` (runs a tool via the permission-gated `ToolExecutor`), `condition` (safe branching via an interpreter with `eq/ne/gt/gte/lt/lte/contains/not_contains`), and `delay`.
- **Structured data flow** between steps: an execution-state document (`input` + per-step `output`) and `input_mapping` resolution so later steps consume earlier steps' output.
- **Condition branching**: a false condition marks the step (and its dependents) `skipped` for deterministic gating.
- **Retry + timeout**: per-step `retry_policy` (exp/fixed backoff) gated by `idempotency` (no auto-retry on `non_idempotent`/`side_effecting`), and per-step `timeout_seconds` → `timed_out`.
- **Step-graph validation** (`app/workflow/validator.py`): unique names, dependency existence, cycle detection, valid agent/tool refs, valid configs.
- **Triggers**: `schedule` (cron via `croniter` or `interval`), `event`, and `webhook` on `workflow_triggers`.
- **DB-as-queue + in-process worker/scheduler**: `workflow_executions` rows (`queued`) claimed atomically by `WorkflowWorker` (`FOR UPDATE SKIP LOCKED` / SQLite select-and-update); `WorkflowScheduler` fires due triggers; `recover_stale()` marks stuck `running` executions `timed_out`. Auto-started with the API when `WORKFLOW_WORKER_ENABLED=true` — durable across restarts, no Redis.
- **Five new tables** (migration `0004`): `workflows`, `workflow_steps`, `workflow_triggers`, `workflow_executions`, `step_executions` (the per-run step trace).
- **API**: full workflow router under `/api/v1/workflows` — workflow CRUD, activate/pause, validate, step/trigger management, execute, and execution history with step traces + cancel.
- **Frontend**: a `/workflows` page (create/edit workflows; add/remove/manage steps and triggers; activate/pause/execute) and a `/workflows/[id]` detail page with a step-trace **visualization** (`WorkflowVisualization`) and execution history.
- Comprehensive tests: condition evaluator, validator, engine (sequential steps, branching, retry, timeout, cancel, max-steps), worker + queue, scheduler, API, and a deterministic "Daily Research Workflow" E2E example.

**Exit criteria (met):** a multi-step workflow with condition branching, structured inter-step data, retry/timeout, and schedule/event/webhook triggers executes end-to-end, persists a full step trace, and is orchestrated durably by a DB-backed worker + scheduler that survive restarts.

## ✅ Phase 4 — Memory System *(completed)*

- **Five memory types** (`app/db/models/memory.py`): `working` (short-term, TTL), `episodic` (past experiences), `semantic` (facts/knowledge), `procedural` (how-to patterns), and `structured` (JSON records). Enums: `MemoryStatus` (active/archived/expired), `MemoryOwnerType` (agent/system), `MemorySourceType` (execution/user_input/tool_output/imported).
- **Single-table storage** with **namespace isolation** and **ownership** — every memory carries a `namespace` (isolation key) plus an optional `owner_id` (agent or system), with composite indexes for scoped, high-perf queries. Migration `0005_memories`.
- **Embedding abstraction** (`app/memory/embedding.py`): an `EmbeddingProvider` protocol (`embed`, `dimensions`) with a deterministic `MockEmbeddingProvider` (for tests/local, no key) and a scaffolded `OpenAIEmbeddingProvider` (deferred). A factory (`get_embedding_provider`) returns a provider only when configured; retrieval degrades gracefully to keyword matching otherwise.
- **Hybrid retrieval** (`app/memory/retrieval.py`) — a `HybridRetriever` scores candidates by weighted `semantic + keyword + recency + importance + confidence` (Dice-coefficient keyword overlap, exponential recency decay, cosine similarity when embeddings exist), exposing a per-result **`breakdown`** for observability. Policies (`app/memory/policies.py`) set the context budget, relevance threshold, per-type multipliers, dedup threshold, TTL, and working-memory cap.
- **Auto-extraction from executions** (`app/memory/extraction.py`): when an agent completes a task, the runtime creates an **episodic** memory (always), a **semantic** memory (on success+output), and a **procedural** memory (when tools were used) — embedded when a provider is present.
- **Runtime integration**: the runtime retrieves relevant memories **before** building context and injects them into the system prompt (typed + importance-labeled), then persists new memories **after** the execution completes. Both are best-effort and non-fatal. Memory access is tracked (count + timestamp).
- **API** (`app/api/v1/endpoints/memories.py`): CRUD on `/api/v1/memories`, hybrid search (`POST /memories/search`), archive, and TTL cleanup (`POST /memories/cleanup`), backed by `MemoryService`.
- **Config** — 15 `memory_*` settings (embedding provider/model/dims, retrieval weights, context budget, thresholds, write policy, TTL, `memory_extraction_enabled`).
- **Frontend** (`apps/web`): a `/memories` page with namespace selector, hybrid search, type/status filter chips, agent owner filter, expandable detail (source, expiry, metadata, importance/confidence), a New-memory form, archive/delete, cleanup-expired, and pagination.
- Comprehensive tests: embedding abstraction, policies (dedup/TTL/budget), hybrid retrieval (keyword/semantic/namespace/owner/type/min-score/breakdown), extraction (success/failure/importance/embeddings), service CRUD/lifecycle, full HTTP API, and runtime integration (auto-extraction + second-run recall).

**Exit criteria (met):** an agent can recall prior context across sessions/tasks — memories are auto-extracted from completed runs, retrieved by hybrid ranking, injected into the next run's context, and isolated by namespace/owner with working-memory TTL expiry.

## ✅ Phase 5 — Multi-Agent Orchestration *(completed)*

Multiple specialized agents now coordinate on a **shared objective** as a team. The engine is deterministic and provider-independent (mock providers run the whole loop with no paid API) and reuses the Agent Runtime, Tool Executor, workflow engine, and Memory from Phases 1–4.

- **Domain (`app/db/models/orchestration.py`, migration `0006_orchestrations`)** — 7 tables: `orchestrations`, `orchestration_tasks`, `agent_assignments`, `agent_messages`, `orchestration_results`, `orchestration_context`, `agent_reviews`. Enums: `OrchestrationStatus` (created→…→completed), `OrchestrationTaskStatus`, `AssignmentStatus`, `AgentMessageType`, `ReviewVerdict`.
- **Planner (`app/orchestration/planner.py`)** — `DeterministicPlanner`: objective → validated `ExecutionPlan` with `required_capabilities` + `dependencies`. Market/competitive objectives decompose into Research → Analysis → Fact-check (parallel) → Writer; anything else falls back to a single general task. Plan refs/cycles validated before any agent runs.
- **Capabilities & selection (`capabilities.py`, `selector.py`)** — canonical capability keys; `resolve_agent_capabilities()` unions role-derived + tool-permission-derived capabilities; `CapabilityAgentSelector` picks the best active agent by coverage with round-robin load-spread across ties.
- **Orchestrator engine (`orchestrator.py`)** — drives the full lifecycle; runs ready tasks in a bounded `ThreadPoolExecutor` (fresh DB session per worker) with dependency-ordered sequencing; a failed task marks only its dependents `skipped`; cancellation is state-machine-guarded. Reuses the Agent Runtime per task.
- **Communication & context (`bus.py`, `messages.py`, `context.py`)** — DB-backed `AgentMessageBus` enforces orchestration authorization; shared facts persist to `orchestration_context` (kind + optional private agent_id) and integrate with Phase 4 Memory; each task gets only task-appropriate inputs.
- **Aggregation (`conflicts.py`, `synthesizer.py`, `review.py`)** — `NumericConflictDetector`, `ResultSynthesizer` (attributed findings/sources/incomplete-tasks/conflicts — never invents data), `AgentReviewService` (verdicts + `max_review_iterations`).
- **State machine (`state_machine.py`)** — explicit legal transitions for orchestration/task/assignment statuses; illegal writes raise `InvalidTransitionError`.
- **Service + API (`orchestration_service.py`, endpoints)** — full API under `/api/v1/orchestrations`: create/list/get/delete/execute/cancel plus tasks, assignments, messages, results, context, timeline, and reviews, backed by `OrchestrationService` serializers.
- **Workflow integration** — `WorkflowStepType.ORCHESTRATION` lets a Phase 3 workflow run an orchestration inline as one of its steps (validator requires `orchestration_id`; engine dispatches it).
- **Frontend (`apps/web`)** — an Orchestrations nav section: a list page (objective, status, task/agent counts, progress, run/cancel, status filter, Create & run form) and a detail page (final result with attributed findings + conflicts, `ExecutionGraph`, metrics, `CollaborationView` for messages/reviews, timeline, results, shared context). Built on the shared `StatusBadge` with no new dependencies.
- **Config** — 14 `orchestration_*` settings (max agents/tasks/parallel, duration/iterations, message/review caps, conflict threshold, memory namespace, sync/inline execution, default strategy).
- **Tests** — 10 dedicated suites (`state_machine`, `planner`, `selector`, `bus`, `conflicts`, `synthesizer`, `review`, `execution`, `integration`, `demo`), SQLite-backed with mock providers. Includes the deterministic **AI Market Research Team** demo proving decompose → parallel team → writer → synthesized final result end-to-end.

**Exit criteria (met):** an objective is decomposed into a validated task graph, each task is assigned to the best-available capability-matched agent, the team executes in parallel + dependency order over an authorized bus, results are aggregated with conflict detection and full source attribution to a synthesized final result, and the whole run is observable (tasks, messages, results, reviews, timeline) in the API and the UI. See [docs/orchestration.md](orchestration.md) for the full reference.

## Phase 6 — AI Employee OS

- Activity feed and live agent telemetry.
- Approvals workflow (human-in-the-loop gates for sensitive actions).
- Audit trail / observability surface (execution, tool-call, latency, cost records).

**Exit criteria:** every agent action is observable and gated where required.

## Phase 7 — AI Company

- Organization/workspace model, settings, and secrets management.
- Authentication and role-based access control (RBAC).
- Multi-provider fleet configuration and shared memory across "employees."

**Exit criteria:** a company workspace operates autonomously with controlled access and stored configuration.

## Phase 8 — Autonomous Business Engine

- Long-running missions with continuous progress toward business goals.
- Self-verification of work, failure detection, and self-healing.
- Cost/latency metrics, evaluation, and performance feedback loops.

**Exit criteria:** NEXUS autonomously drives a defined business mission with monitoring and measurable performance.

## Phase 9 — Evaluation, Security & Production Hardening

- Agent/task evaluation harnesses.
- Environment isolation, sandboxing, and side-effect containment.
- Scale-out, deployment (Kubernetes), and production observability.
- Monetization / multi-tenant hooks.

**Exit criteria:** production-ready reliability, security, and cost controls for real workloads.

---

## Architecture Requirement Areas (design constraints for all phases)

The following 22 capability areas drive the architecture. Each is designed in Phase 0 to be implementable without rewrites; none are built prematurely.

| # | Capability Area | Phase(s) | Architectural Accommodation |
|---|----------------|----------|---------------------------|
| 1 | Automation & Workflow Engine | 3 | Built: `app/workflow/` engine + validator + conditions + DB-backed worker/scheduler; `workflows`, `workflow_steps`, `workflow_triggers`, `workflow_executions`, `step_executions` tables |
| 2 | Mission System | 1 | `missions` table design placeholder in data model; CRUD endpoint pattern |
| 3 | Agent Runtime | 1 | `ModelProvider` abstraction + registry; agent reasoning loop interface |
| 4 | Multi-Agent Communication | 5 | Event/message bus interface via Redis pub/sub or similar |
| 5 | Tool & Action System | 2 | Built: `app/tools/` registry + executor + `PermissionContext`; built-in tools; `tool_calls` + `agent_tool_permissions` tables |
| 6 | Browser Automation & Computer Use | 3 | Sandbox execution interface; isolated container runtime |
| 7 | Memory Architecture | 4 | Built: `app/memory/` embedding abstraction + hybrid retriever + policies + extraction; single `memories` table (5 types, namespace isolation, ownership, TTL); runtime retrieval+injection and post-execution extraction; `/api/v1/memories` API + `/memories` UI |
| 8 | Verification & Self-Correction | 8 | Verification hooks in agent loop; evaluation pipeline interface |
| 9 | Failure Recovery & Resilience | 3 | Built (partial): per-step `retry_policy` gated by `idempotency`; worker `recover_stale()`; dead-letter queue + circuit breaker future |
| 10 | Permission & Security System | 7 | RBAC model; auth middleware; policy engine interface |
| 11 | Human-in-the-Loop Gates | 6 | Approval workflow model; webhook/callback pattern for external input |
| 12 | Observability & Telemetry | 6 | Structured logging; execution tracing; `execution_id` propagation |
| 13 | Evaluation & Benchmarking | 8 | Evaluation harness interface; metrics collection in agent loop |
| 14 | AI Employee Model | 6 | Employee schema (role, permissions, status, schedule); dashboard integration |
| 15 | AI Company Layer | 7 | Organization/workspace model; multi-tenancy via tenant_id |
| 16 | Dynamic Agent Creation | 1 | Agent factory pattern; runtime agent spawning from mission decomposition |
| 17 | Resource & Budget Management | 7 | Token/cost tracking in `ModelResponse.usage`; budget limits in config |
| 18 | Feedback Loops & Learning | 8 | Feedback collection interface; evaluation scoring pipeline |
| 19 | Simulation & Sandbox | 9 | Isolated execution environments; container-per-agent pattern |
| 20 | Agent Marketplace | 9 | Agent template registry; publish/subscribe pattern for agent definitions |
| 21 | Closed-Loop Autonomous Business | 8 | Long-running mission engine; goal-tracking state machine |
| 22 | Cross-Cutting: Config, Secrets, Auth | 7 | `pydantic-settings` config; env-based secrets; auth middleware |

---

## Guiding Principles for Every Phase

1. **Verify before advancing.** Each phase ends with tests + a working demo.
2. **Provider- and vendor-agnostic.** No vendor lock-in in application logic.
3. **Secure by default.** Boundaries between reasoning, tool use, and side effects.
4. **Observable.** Traceability (IDs, status, latency, cost) from the first agent run.
5. **No premature construction.** Build only what the current phase needs.
