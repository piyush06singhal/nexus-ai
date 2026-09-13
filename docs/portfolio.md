# NEXUS — Portfolio

**A complete AI workforce, company, and autonomous startup — not a chatbot.**

NEXUS hands a high-level business objective to a system of AI agents that
plans, coordinates, and executes toward it. It composes twelve phases
(0–12) of layered capabilities into a single platform.

> NEXUS is **systems engineering**, not an AI chatbot. A chatbot answers a
> prompt; NEXUS provisions a workforce, scopes it inside a company,
> governs its autonomy, verifies its work, heals its failures, and simulates
> what happens next — then recommends, never auto-replaces.

---

## 1. Layered Architecture (Bottom → Top)

| Layer | What it does | Key service |
|-------|--------------|-------------|
| **Foundation** (Phase 0) | Monorepo: `apps/api` (FastAPI + SQLAlchemy), `apps/web` (Next.js), `infrastructure/docker`, Alembic (`0014_phase12_sim_opt_mkt`) | `app/core`, `app/db` |
| **AI abstraction** | Provider registry (`openai`, `anthropic`, `mock`) — deterministic `MockProvider` for tests | `app/ai/providers/*` |
| **Agent Runtime** (Phase 1) | `validate → build_context → tool loop (generate→tool_calls)→ parse → persist` | `app/runtime/runtime.py` |
| **Tool & Action System** (Phase 2) | Permission-gated registry, 4 built-ins, `ToolExecutor`, SSRF + prompt-injection guards | `app/tools` |
| **Workflow Orchestration** (Phase 3) | Agent/control/tool/delay steps, topo-sorted engine, DB-as-queue worker + scheduler | `app/workflow` |
| **Memory** (Phase 4) | 5 types (working/episodic/semantic/procedural/knowledge), hybrid retrieval, namespace isolation, auto-extraction | `app/memory` |
| **Multi-Agent Orchestration** (Phase 5) | Planner → Selector → Orchestrator (parallel + dependency-ordered over message bus) → Synthesizer (conflict + attribution) | `app/orchestration` |
| **Verification / Recovery / Evaluation** (Phase 6) | Verify correctness, bounded self-healing (`max_retries=2` etc.), escalation, regression detection | `app/verification`, `app/recovery`, `app/evaluation` |
| **AI Employee OS** (Phase 7) | Identity, skills, goals, workload, assignment engine, performance, templates, audit | `app/employee` |
| **AI Company Layer** (Phase 8) | Companies, departments, org chart, KPIs (from authoritative data), budgets, policies (most-restrictive-wins), risks/alerts/health | `app/company` |
| **Autonomous Startup Engine** (Phase 9) | Mission → plan → bootstrap → operate (cycles) → feedback → replan, approval gates, bounded-autonomy governance | `app/startup` |
| **External Integrations & Computer Use** (Phase 10) | Integrations as permission-gated tools, immutable external-action journal (`risk→policy→approval→execution→verification→recovery→audit`), reference-only credentials, bounded simulated browser/computer sessions with untrusted-observation labels, SSRF/webhook hardening | `app/external` |
| **Security, Governance & Production Hardening** (Phase 11) | Fernet AES-256-GCM secrets, HS256 auth, RBAC/ABAC + policy engine, hash-chained audit, 13-category detection→alerts→incidents, kill switch, resource/approval/break-glass governance, telemetry/metrics/redaction/middleware/DLQ/health-probes, `production_readiness` gate | `app/security` |
| **Simulation, Optimization & Agent Marketplace** (Phase 12) | Closed-sandbox simulation (SIMULATED/FORECAST never ACTUAL), weighted multi-objective optimization behind an `ApprovalGateManager` gate, approval-gated experiments (WINNER/LOSER/INCONCLUSIVE), 8-dimension benchmarking, internal metadata-only marketplace (`PackageScanner`, approval-gated install, evidence-based recommendations), closed-loop `OBSERVE→SIMULATE→OPTIMIZE→PROPOSE→APPROVE→EXECUTE→MEASURE→LEARN` | `app/phase12` |

Every table carries `company_id UUID FK + index` → tenant isolation.

---

## 2. Reliability Engineering

- **Verification layer** — shared, determines correctness before recovery is attempted.
- **Recovery engine** — bounded budgets (`max_retries=2`, `max_runtime_seconds`, `tool_call_budget`), self-heals safe failures, escalates the rest.
- **Evaluation** — post-execution regression detection (`EVALUATION_REGRESSION_THRESHOLD=0.05`).
- **Worker reliability** — heartbeats (`5s`), stale threshold (`120s`), `MAX_RETRIES=3`, idempotency, DLQ.
- **Health** — unauthenticated `/api/v1/health/{live,ready,dependencies}` + auth-bound `/api/v1/system/health/*`; compose healthchecks via Python/Node fetch.

## 3. Governance & Observability

- **Approval gates** — every governed proposal (autonomy, optimization, marketplace install, loop cycle) waits for a human decision at `/approvals` → `ApprovalGateManager.approve/reject`. One gate = one action; never future-widens autonomy.
- **Kill switches & limits** — global `KILL_SWITCH_GLOBAL_PAUSE`; per-scope `SystemFlag`; per-category `ResourceLimit` (iterations, duration, tokens, cost, tool_calls, plus Phase 12's `sim_runs/iterations/events`, `optimization_candidates`, …).
- **Audit** — append-only hash-chained log (`/api/v1/security/audit`, `/audit/verify`).
- **Telemetry** — `ContextVar` request/trace IDs (`app/core/telemetry.py`), metrics registry (`app/core/metrics.py`), central redaction filter.

## 4. External Integrations (Governed)

Reference-only credentials — `INTEGRATION_<PROVIDER>_SECRET` resolved at use-time from env, never in DB. Every external action is `risk→policy→approval→execution→verification→recovery→audit`. Browser/computer sessions are bounded, simulated, and observations labeled **UNTRUSTED**.

## 5. Simulation → Optimization → Marketplace → Closed Loop

- Simulation is deterministic by default, seeded Monte-Carlo on demand; outputs are forecasts, not commitments. No production table is mutated.
- Optimization rejects policy/budget-violating candidates, then ranks the survivors. The **recommendation** ships with a 10-part explainability block (`what/why/alternatives/constraints/why_this_candidate/…`) — and stops. **Governance decides.**
- Marketplace is internal and metadata-only; installation is approval-gated. Recommendations are evidence-ranked (real benchmark scores).
- The closed loop chains OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE → EXECUTE → MEASURE → LEARN and reuses Phase 9 gates + Phase 11 budgets — 43 additive tables behind `/api/v1/simulations`, `/optimization`, `/experiments`, `/benchmarks`, `/marketplace`, `/agent-recommendations`, `/optimization-cycles`.

## 6. Measurement

| Signal | Value |
|--------|-------|
| Backend tests | 1085+ across 94 files (file-backed SQLite, deterministic `MockProvider`) |
| Frontend tests | 141 (vitest) |
| Lint | `ruff` (backend), `eslint` + `tsc --noEmit` (frontend) |
| Build | Next.js 16 production `npm run build` |
| CI | Backend (ruff, format, pytest) + Frontend (lint, tsc, vitest, build) + Docker build + `alembic upgrade→downgrade→upgrade` round-trip + non-blocking `production_readiness` report |
| Health probes | `curl -sf localhost:8000/api/v1/health/{live,ready,dependencies}` (0 secrets leaked) |
| Perf baseline | `python -m scripts.perf_baseline` — dev-environment measurements (e.g., agent exec ~4ms, tool loop ~5ms, simulation ~3ms — **not SLAs**) |
| App (`docker compose up`) | Auto-migrates (`AUTO_MIGRATE`, `docker-entrypoint.sh`), `unless-stopped`, api/redis/postgres healthchecks |

## 7. Engineering Practices

- Deterministic doubles everywhere (`MockProvider`, scripted `generate`, seeded simulation).
- `company_id` on every table for isolation.
- Idempotent seeds: `scripts.seed_company / _autonomous_startup / _external_ops / _security_governance / _simulation_optimization` (dependency-ordered) — rerun safe.
- Honest labels: `SIMULATED`/`FORECAST` outputs, `RECOMMENDATION` language in the UI, warnings on `FORCED` decisions.

---

## 8. What NEXUS Is Not

- **Not in production.** No deployed topology, no real traffic, no cost observability in anger.
- **No compliance certification.** See `docs/security.md` for the actual threat model and controls — not SOC2/HIPAA/FedRAMP claims.
- **No SLA.** Numbers in ` docs/operations.md` (§42) are local measurements on SQLite + Mock.
- **No self-modification / RL.** No auto-production-replacement; no learning loop that changes behavior without approval.
- **No public package ecosystem.** Marketplace is internal reference/benchmark, not npm/PyPI.
- **Not a chat UI.** The web app is shells + operations pages over the same governed API — the value is the engine.

---

**Run it:** `docker compose up --build` (then `bash scripts/run_demos.sh` for the full seeded demo).
**Read the demo:** `docs/demo.md` (14-item §49 checklist, correct for the live build).
**Read the truth:** `docs/final-readiness.md` (§54 — what passed, what remains limited, and why).
