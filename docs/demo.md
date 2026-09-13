# NEXUS — Demo Guide

**Audience:** evaluator, reviewer, or stakeholder running the full demo locally.
**Scope:** this document is the reviewer's checklist (§49) and the end-to-end
smoke path (§50). Every item is mapped to an exact command, UI page, and
expected outcome with honest labeling (ACTUAL / SIMULATED / FORECAST /
RECOMMENDATION).

---

## Prerequisites

```bash
# From repo root
docker compose up -d postgres redis
# Optional: if you prefer a local venv (default in run_demos.sh):
# cd apps/api && python -m venv .venv && .venv/bin/pip install -e .
```

---

## One-Command Full Demo

```bash
bash scripts/run_demos.sh
```

This:
1. Starts Postgres (5433) + Redis containers
2. Runs `alembic upgrade head` on the docker Postgres
3. Executes all 5 seed scripts in dependency order with `--reset`
4. Starts a local API on 127.0.0.1:8000
5. Waits for `/api/v1/health/ready` → 200
6. Runs Phase 11 smoke (`scripts.smoke_api --phase 11`) — 0×5xx
7. Runs Phase 12 smoke (`scripts.smoke_api --phase 12`) — 0×5xx

When it finishes, the summary block prints the URLs and confirms both smokes passed.

---

## 14-Item Reviewer's Checklist (§49)

Each item: **#** → **What** → **Seed / Command** → **UI Page** → **Expected** → **Label**.

| # | Capability | Seed / Command | UI Page | Expected | Label |
|---|------------|----------------|---------|----------|-------|
| 1 | **Company layer** — departments, org chart, KPIs, budgets, policies, risks, alerts, health score | `seed_company --reset` (creates "NEXUS Labs") | `/settings` (health snapshot), `/companies/{id}` (detail) | 6 departments, 6 employees, KPIs computed from authoritative data, budgets cascaded, policies with most-restrictive-wins, health score 0–100 | ACTUAL |
| 2 | **Agent execution** — single task, tool loop, persistence | Phase 1/2 in `seed_company` | `/agents`, `/agents/{id}/executions` | MockProvider returns deterministic JSON; execution persisted with tool calls | ACTUAL |
| 3 | **Workflow orchestration** — topo-sorted steps, DB-as-queue worker | `seed_company` | `/workflows`, `/workflows/{id}/steps` | Steps execute in dependency order; trace recorded | ACTUAL |
| 4 | **Memory** — 5 types, hybrid retrieval, namespace isolation | `seed_company` | `/memory` (namespace filter) | Memories of each type stored; search returns ranked results | ACTUAL |
| 5 | **Multi-agent orchestration** — Planner → Selector → Orchestrator → Synthesizer | `seed_company` | `/orchestration/teams` | Planner decomposes, selector picks agents, orchestrator runs parallel, synthesizer aggregates | ACTUAL |
| 6 | **Verification / Recovery / Evaluation** — bounded self-heal, escalation, regression detection | `seed_company` | `/verification`, `/recovery`, `/evaluation` | Verify runs before recovery; max_retries=2 budget; regressions flagged | ACTUAL |
| 7 | **AI Employee OS** — identity, skills, goals, workload, assignment, performance, templates | `seed_company` | `/employees`, `/employees/{id}` | 6 employees with skills/goals; workload tracked; assignment engine scores | ACTUAL |
| 8 | **Autonomous Startup Engine** — mission → strategic plan → bootstrap → cycles → feedback → replan | `seed_autonomous_startup --reset` ("NEXUS Autonomous AI Startup") | `/autonomy/{company_id}/gates` (pending approvals), `/startup/plans` | Mission analyzed; startup plan generated; approval gate waits at `/approvals` | RECOMMENDATION |
| 9 | **External Integrations** — governed funnel, reference-only credentials, simulated browser/computer, UNTRUSTED labels | `seed_external_ops --reset` ("NEXUS External Operations") | `/external/actions`, `/external/sessions` | Research demo (simulated browser), dev issue read, campaign draft/send — all through `risk→policy→approval→exec→verify→recover→audit` | SIMULATED |
| 10 | **Security / Governance** — HS256 auth, RBAC/ABAC, policy engine, Fernet secrets, prompt-injection/SSRF guards, kill switch, resource limits, hash-chained audit | `seed_security_governance --reset` ("NEXUS Security & Governance") | `/security/audit`, `/governance/flags`, `/governance/limits`, `/security/incidents` | Audit chain verifies; kill-switch pauses tenant; resource limits enforce; 13-category detection fires alerts | ACTUAL |
| 11 | **Simulation** — deterministic sandbox, seeded Monte-Carlo, digital-twin snapshots, baseline-vs-scenario | `seed_simulation_optimization --reset` ("NEXUS Simulation & Optimization") Part 1 | `/simulations`, `/simulations/{id}/results` | What-if: 5→7 employees; outputs labeled **SIMULATED** (deterministic) or **FORECAST** (Monte-Carlo) | SIMULATED / FORECAST |
| 12 | **Optimization** — multi-objective (greedy/exhaustive/ranking), policy/budget filter, 10-part explainability, approval gate | `seed_simulation_optimization` Part 2–4 | `/optimization/recommendations` (PENDING → `/approvals`), `/optimization/cycles` | Candidate rejected if violates policy/budget; surviving ranked; recommendation ships explainability block → gate | RECOMMENDATION |
| 13 | **Agent Marketplace** — metadata-only, PackageScanner, evidence-based recs, approval-gated install | `seed_simulation_optimization` Part 5 | `/marketplace/packages`, `/marketplace/recommendations`, `/marketplace/install` | Packages scanned; recommendations ranked by benchmark scores; install records intent only | RECOMMENDATION |
| 14 | **Closed Loop** — OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE → EXECUTE → MEASURE → LEARN | `seed_simulation_optimization` Part 6 | `/optimization-cycles`, `/agent-recommendations` | One full cycle runs; `ApprovalGateManager` decides; post-execution evaluation feeds next cycle | RECOMMENDATION |

**Label meanings:**

- **ACTUAL** — real code path executed against the database; persisted data is authoritative.
- **SIMULATED** — deterministic sandbox run; no production tables mutated; labeled in API response.
- **FORECAST** — Monte-Carlo iteration within the sandbox; distribution outputs, never commitments.
- **RECOMMENDATION** — optimization/marketplace/cycle output that stops at an approval gate; governance decides.

---

## End-to-End Smoke Path (§50)

### Automated (via `scripts/run_demos.sh`)

```bash
# After the full demo stack is up:
curl -sf http://127.0.0.1:8000/api/v1/health/live      # → 200
curl -sf http://127.0.0.1:8000/api/v1/health/ready     # → 200
curl -sf http://127.0.0.1:8000/api/v1/health/dependencies
# → JSON with db/redis/ai_provider/worker status (no secrets)

# Phase 11 prefixes (all 2xx/3xx or expected 401/404):
.venv/bin/python -m scripts.smoke_api --phase 11  # 0×5xx

# Phase 12 prefixes (all 2xx/3xx or expected 401/404):
.venv/bin/python -m scripts.smoke_api --phase 12  # 0×5xx
```

### Manual Walkthrough (Browser)

1. **Open the web app:** `http://localhost:3000` (requires `docker compose up -d web`)

2. **Health probes (no auth):**
   - `GET /api/v1/health/live` → `{ "status": "ok" }`
   - `GET /api/v1/health/ready` → `{ "status": "ready", "checks": [...] }`
   - `GET /api/v1/health/dependencies` → `{ "dependencies": [ { "name": "database", "status": "ok" }, { "name": "redis", "status": "ok" }, { "name": "ai_provider", "status": "configured|not_configured" }, { "name": "worker", "status": "ok|degraded" } ] }`

3. **Approvals page (`/approvals`):**
   - Lists pending **autonomy approval gates** (from Phase 9) and **optimization recommendations** (Phase 12, status PENDING)
   - Each row: title, type, requested action, approve/reject buttons
   - Clicking "Approve" calls the real API and refreshes the list

4. **Settings page (`/settings`):**
   - Runtime environment + version
   - Health probe status (live/ready/dependencies)
   - Feature flags from `/api/v1/system/feature-flags`
   - Kill-switch scopes from `/api/v1/governance/flags`
   - Resource limits from `/api/v1/governance/limits`
   - **No keys, tokens, or ciphertext are rendered**

5. **Security audit (`/security/audit`):**
   - `GET /api/v1/security/audit?company_id=<demo>&limit=50`
   - `GET /api/v1/security/audit/verify?company_id=<demo>` → `{ "valid": true }` or tamper index

6. **Simulation results (`/simulations`):**
   - Filter by `simulation_type` (WHAT_IF / MONTE_CARLO / DIGITAL_TWIN / BASELINE_COMPARISON)
   - Every result object carries `"output_label": "SIMULATED"` or `"FORECAST"`

7. **Optimization recommendations (`/optimization/recommendations`):**
   - Status: PENDING / APPROVED / REJECTED / APPLIED
   - Expand row → 10-part explainability block:
     `what`, `why`, `alternatives`, `constraints`, `why_this_candidate`,
     `risk_mitigation`, `rollback_plan`, `assumptions`, `confidence`, `decision_needed`

8. **Marketplace (`/marketplace`):**
   - Packages listed with `PackageScanner` validation status
   - Recommendations show attached benchmark scores (not vendor claims)
   - Install → approval gate → intent recorded; execution goes through normal governance

9. **Performance baseline (terminal):**
   ```bash
   cd apps/api && .venv/bin/python -m scripts.perf_baseline
   ```
   Prints markdown table (dev-environment measurements, **not SLAs**).

---

## Expected Non-Errors (Do Not File)

| Endpoint / Scenario | Expected Non-2xx | Reason |
|---------------------|------------------|--------|
| `GET /api/v1/companies/{nonexistent}` | 404 | ID has no row; `_company_or_404` convention |
| `GET /api/v1/optimization/recommendations/{id}/approve` (already APPLIED) | 409 | Idempotent: already applied |
| `GET /api/v1/health/ready` when Postgres down | 503 | Correct readiness signal |
| Any protected endpoint with `AUTH_ENABLED=true` and no token | 401 | Auth working |
| WebSocket `/ws` endpoints | 404 or 426 | Not implemented in demo; HTTP only |

---

## Troubleshooting the Demo

| Symptom | Fix |
|---------|-----|
| `docker compose up` hangs on "starting" | `docker compose ps` — check postgres/redis health; if stuck, `docker compose down -v` and re-run |
| `alembic upgrade head` fails: "Target database is not up to date" | `alembic downgrade base && alembic upgrade head` (round-trip) |
| `smoke_api --phase 11` shows 5xx | Check API logs (`docker compose logs api` or uvicorn output); ensure migrations applied |
| `/approvals` page empty | Ensure `seed_autonomous_startup` and `seed_simulation_optimization` ran (they create pending gates) |
| Web dev server not hot-reloading | `npm run dev` in `apps/web`; check `node -v` is 24+ |

---

## Running Subsets

```bash
# Single seed (after infra + migrations):
cd apps/api && .venv/bin/python -m scripts.seed_company --reset

# Just the health probes (no seeds):
curl -sf http://127.0.0.1:8000/api/v1/health/live
curl -sf http://127.0.0.1:8000/api/v1/health/ready
curl -sf http://127.0.0.1:8000/api/v1/health/dependencies

# Only Phase 12 smoke (requires Phase 12 seeds to have run):
.venv/bin/python -m scripts.smoke_api --phase 12

# Performance baseline (no docker needed; uses SQLite):
cd apps/api && .venv/bin/python -m scripts.perf_baseline
```

---

## What Is Not In The Demo

- **No real LLM calls** — all providers use `MockProvider` (deterministic JSON).
- **No production traffic** — the API runs single-process uvicorn on localhost.
- **No compliance certifications** — controls are implemented; audits are not claimed.
- **No real browser sessions** — Phase 10 browser/computer use is a deterministic simulation.
- **No public marketplace** — packages are metadata-only references for internal benchmarking.

---

## Reference Links

- `scripts/run_demos.sh` — the canonical demo runner
- `docs/portfolio.md` — portfolio narrative
- `docs/case-study.md` — problem → architecture → limitations
- `docs/operations.md` — startup, health, logs, workers, config, perf baseline
- `docs/security.md` — threat model, authZ, secrets, audit, incident response
- `docs/final-readiness.md` — final engineering report (readiness classification)