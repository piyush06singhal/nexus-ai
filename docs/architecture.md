# NEXUS — System Architecture

> **Phase 0 (Foundation).** This document describes the current architecture and the design decisions that will shape the system as it grows. Later phases build new components on this foundation; sections marked *future* describe intent, not existing functionality.

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
   (dashboard shell) ──▶ │  Next.js · React · Tailwind │
                         └──────────────┬──────────────┘
                                        │  /api/*  (Next rewrite proxy, same-origin)
                                        ▼
                         ┌─────────────────────────────┐
                         │        NEXUS API            │
                         │  FastAPI · Pydantic         │
                         │  /api/v1                    │
                         └───┬───────────────┬─────────┘
                             │               │
                 ┌───────────▼───┐   ┌───────▼────────┐
                 │  PostgreSQL   │   │     Redis      │
                 │  SQLAlchemy   │   │  (future cache │
                 │  Alembic      │   │   & queues)    │
                 └───────────────┘   └────────────────┘

        (Future: AI Provider adapters resolve through the model abstraction;
         the agent runtime, task engine, memory, and orchestration build on
         this foundation in later phases.)
```

---

## 3. Major Components & Responsibilities

### 3.1 Frontend (`apps/web`)

- Next.js (App Router), React, Tailwind CSS, TypeScript (strict).
- A dashboard **shell**: sidebar navigation (Dashboard, Missions, Agents, Tasks, Activity, Approvals, Settings) and a top header.
- Every unfinished area renders a clear **placeholder** — no fake AI functionality.
- The `SystemStatus` widget fetches `/api/v1/health` to show live backend/database/Redis status.
- API calls are same-origin, proxied to the backend by a runtime route handler (`app/api/[...path]/route.ts`).

### 3.2 Backend (`apps/api`)

FastAPI application with:

- **Entry point** (`app/main.py`) — app factory, lifespan hook, CORS, router mounting, exception handlers.
- **Configuration** (`app/core/config.py`) — pydantic-settings `Settings` singleton driven by environment variables and `.env`.
- **Database** (`app/db/`) — SQLAlchemy engine/session, a naming-convention declarative `Base`, and Alembic migrations. Phase 0 ships a minimal `agents` table to prove the pipeline.
- **API versioning** (`app/api/v1/`) — v1 endpoints mounted under `/api/v1`. Future versions are additive.
- **Health endpoint** (`app/api/v1/endpoints/health.py`) — always returns 200 when reachable; individual checks degrade rather than failing the request.
- **Error handling** (`app/core/errors.py`) — typed exception hierarchy rendered as a consistent JSON envelope; no internals leaked to clients.
- **Logging** (`app/core/logging.py`) — structured, namespaced logging.
- **Redis** (`app/core/redis.py`) — lazy client; Redis absence never blocks startup.

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

### 3.4 Infrastructure & Database

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
| Observability | `ModelResponse` carries `latency_ms`, `usage`, timestamps; execution IDs are planned | Readiness without building a platform yet. |
| Security | non-root Docker users; secrets strictly in env; no `.env` committed | Least-privilege and no-secret-commit from day one. |

---

## 6. Data Model (Phase 0)

Phase 0 intentionally creates **only** an `agents` table (a stub proving the ORM + Alembic pipeline). The schema is designed to extend to:

- `users`, `organizations` — tenancy and identity
- `missions` — high-level objectives
- `agents` — AI workers (exists as a stub)
- `tasks` — units of work
- `tools` — executable capabilities
- `executions` — traceable runs with IDs, status, latency, costs
- `memories` — short/long-term state
- `approvals` — human-gate checkpoints
- `evaluations` — agent performance

These arrive incrementally; none are created prematurely.

---

## 7. Capability Accommodation Matrix

The 22 architecture requirement areas drive NEXUS's long-term design. Each is designed in Phase 0 to be implementable without rewrites; none are built prematurely. This matrix shows how each capability is architecturally accommodated from day one.

### 7.1 Automation & Workflow Engine

- **Phase:** 4 (Multi-Agent Orchestration)
- **Design accommodation:** A task queue interface (`app/tasks/`) with a worker process abstraction. The current `SessionLocal` and Redis client establish the pattern for DB-backed queues and pub/sub event dispatch.
- **Interface points:** `TaskQueue.submit()`, `TaskQueue.claim()`, `TaskQueue.complete()` — to be implemented with Redis or Postgres advisory locks.

### 7.2 Mission System

- **Phase:** 1 (Agent Runtime)
- **Design accommodation:** The `missions` table design placeholder exists in the data model (Section 6). The `agents` stub table proves the ORM + Alembic pipeline that `missions` will follow. CRUD endpoint pattern established by the health endpoint structure.
- **Interface points:** `Mission` model, `MissionService`, `POST /api/v1/missions`, `GET /api/v1/missions/{id}`.

### 7.3 Agent Runtime

- **Phase:** 1 (Agent Runtime)
- **Design accommodation:** The `ModelProvider` Protocol and registry (`app/ai/`) provide the core abstraction. The reasoning loop (`generate` → act → repeat) will be implemented as an `AgentRunner` that consumes `ModelProvider` and `ToolRegistry`.
- **Interface points:** `ModelProvider.generate()`, `ModelProvider.stream()`, `ModelProvider.structured_output()`. The `AgentRunner` class orchestrates the loop.

### 7.4 Multi-Agent Communication

- **Phase:** 4 (Multi-Agent Orchestration)
- **Design accommodation:** Redis pub/sub or a dedicated message bus. The existing `get_redis_client()` in `app/core/redis.py` establishes the connection pattern. Agent-to-agent messages will use an event schema with `execution_id` propagation.
- **Interface points:** `EventBus.publish()`, `EventBus.subscribe()`. Events carry `execution_id` for tracing.

### 7.5 Tool & Action System

- **Phase:** 2 (Tool System)
- **Design accommodation:** A tool registry pattern where each tool is a typed, sandboxed capability. The permission boundary between agent reasoning and tool side effects is enforced at the registry level.
- **Interface points:** `ToolRegistry.register()`, `ToolRegistry.execute()`, `Tool` protocol with `name`, `description`, `parameters`, `execute()`.

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

- **Phase:** 4 (Multi-Agent Orchestration)
- **Design accommodation:** Retry patterns with exponential backoff, dead-letter queues for failed tasks, and circuit breaker interfaces for external service calls.
- **Interface points:** `RetryPolicy`, `DeadLetterQueue`, `CircuitBreaker`.

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

- **Phase 1+ (Agent Runtime):** real provider adapters (OpenAI, Anthropic, Gemini, local); agent reasoning loop; structured outputs.
- **Task engine:** a DB-backed queue and worker process, with `execution_id` observability.
- **Tool system:** a sandboxed tool-execution boundary with authorization gating.
- **Memory:** short-term (context/conversation) and long-term (vector/searchable) stores.
- **Multi-agent orchestration:** mission decomposition, role assignment, coordination, retries, failover.
- **Approvals & RBAC:** human-in-the-loop gates for sensitive side effects.

See [roadmap.md](roadmap.md) for the full phased plan.