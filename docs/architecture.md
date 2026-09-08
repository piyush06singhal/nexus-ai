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
- API calls are same-origin, proxied to the backend by a `next.config.ts` rewrite.

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
| Web→API | same-origin proxy rewrite | Avoids CORS entirely in dev and Docker. |
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

## 7. Future Architecture (later phases)

- **Phase 1+ (Agent Runtime):** real provider adapters (OpenAI, Anthropic, Gemini, local); agent reasoning loop; structured outputs.
- **Task engine:** a DB-backed queue and worker process, with `execution_id` observability.
- **Tool system:** a sandboxed tool-execution boundary with authorization gating.
- **Memory:** short-term (context/conversation) and long-term (vector/searchable) stores.
- **Multi-agent orchestration:** mission decomposition, role assignment, coordination, retries, failover.
- **Approvals & RBAC:** human-in-the-loop gates for sensitive side effects.

See [roadmap.md](roadmap.md) for the full phased plan.