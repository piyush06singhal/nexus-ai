# NEXUS — Roadmap

The platform is built incrementally, phase by phase. Each phase ships verifiable functionality and is validated before the next begins. **Marked items in later phases are planned, not yet built — nothing beyond Phase 0 currently exists.**

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

**Exit criteria:** frontend, backend, Postgres, Redis all start; frontend talks to backend; health + migrations + tests + lint/typecheck all pass; Docker Compose works; docs accurate; no secrets committed.

---

## 🔜 Phase 1 — Agent Runtime

- Real model provider adapters behind the abstraction (OpenAI, Anthropic, Gemini, local).
- Core data models: full `agents`, `missions`, `tasks` + CRUD APIs + ORM tests.
- A basic **agent reasoning loop** (`generate` → act → repeat) against tools, with structured outputs validated by Pydantic.

**Exit criteria:** an agent can complete a scripted task using a real or stubbed provider, with a typed, traced call path.

## Phase 2 — Tool System

- Executable **tools** as typed, sandboxed capabilities.
- Permission/authorization boundary between agent reasoning and tool side effects.
- Tool registry, argument validation, and failure handling.

**Exit criteria:** an agent can invoke approved tools safely; sensitive tools require authorization.

## Phase 3 — Memory

- **Short-term** memory (conversation/context window management).
- **Long-term** memory (persistent, searchable storage).
- Memory retrieval integrated into the agent loop.

**Exit criteria:** an agent can recall prior context across sessions/tasks.

## Phase 4 — Multi-Agent Orchestration

- Mission planning and **task decomposition**.
- Role/agent assignment and inter-agent coordination.
- Task queue + worker runtime with `execution_id` observability, retries, and failover.

**Exit criteria:** a mission is decomposed and executed across multiple agents with full traceability.

## Phase 5 — AI Employee OS

- Activity feed and live agent telemetry.
- Approvals workflow (human-in-the-loop gates for sensitive actions).
- Audit trail / observability surface (execution, tool-call, latency, cost records).

**Exit criteria:** every agent action is observable and gated where required.

## Phase 6 — AI Company

- Organization/workspace model, settings, and secrets management.
- Authentication and role-based access control (RBAC).
- Multi-provider fleet configuration and shared memory across "employees."

**Exit criteria:** a company workspace operates autonomously with controlled access and stored configuration.

## Phase 7 — Autonomous Business Engine

- Long-running missions with continuous progress toward business goals.
- Self-verification of work, failure detection, and self-healing.
- Cost/latency metrics, evaluation, and performance feedback loops.

**Exit criteria:** NEXUS autonomously drives a defined business mission with monitoring and measurable performance.

## Phase 8 — Evaluation, Security & Production Hardening

- Agent/task evaluation harnesses.
- Environment isolation, sandboxing, and side-effect containment.
- Scale-out, deployment (Kubernetes), and production observability.
- Monetization / multi-tenant hooks.

**Exit criteria:** production-ready reliability, security, and cost controls for real workloads.

---

## Guiding Principles for Every Phase

1. **Verify before advancing.** Each phase ends with tests + a working demo.
2. **Provider- and vendor-agnostic.** No vendor lock-in in application logic.
3. **Secure by default.** Boundaries between reasoning, tool use, and side effects.
4. **Observable.** Traceability (IDs, status, latency, cost) from the first agent run.
5. **No premature construction.** Build only what the current phase needs.