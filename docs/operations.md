# NEXUS — Operations Guide

**Status**: Development environment. No production deployment history. All
measurements are development-environment measurements on local Docker/PostgreSQL
— **not SLAs**.

---

## 1. Quick Start (One-Command Stack)

```bash
# From repo root
cp .env.example .env         # edit if needed
docker compose up --build -d
# API:  http://localhost:8000  (docs at /docs)
# Web:  http://localhost:3000
# DB:   postgresql://nexus:nexus_dev@localhost:5433/nexus
```

The API container entrypoint (`infrastructure/docker/docker-entrypoint.sh`)
runs `alembic upgrade head` automatically on startup. Opt out with
`AUTO_MIGRATE=false` in `.env`.

---

## 2. Startup Sequence (Manual / Local Dev)

```bash
# 1. Infrastructure
docker compose up -d postgres redis

# 2. Migrations (from apps/api)
.venv/bin/alembic upgrade head

# 3. API (background)
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# 4. Web (separate terminal, from apps/web)
npm run dev
```

---

## 3. Database Migrations

- Alembic head: `0014_phase12_sim_opt_mkt` (26-char revision)
- Env-driven: `alembic/env.py` reads `settings.database_url` from `DATABASE_URL`
- Round-trip tested in CI: `upgrade head` → `downgrade base` → `upgrade head`
- Seed order (dependency-ordered):
  1. `seed_company`
  2. `seed_autonomous_startup`
  3. `seed_external_ops`
  4. `seed_security_governance`
  5. `seed_simulation_optimization`
- All seeds accept `--reset` (deletes their demo company, re-creates)

---

## 4. Backups & Recovery

See `disaster-recovery.md` for the full plan. Summary:

| Aspect | Value |
|--------|-------|
| **RPO** | Point-in-time (WAL) — requires managed Postgres with PITR |
| **RTO** | Depends on restore method; local `pg_restore` ≈ minutes |
| **Automated** | Not configured — deployment concern |

Local dev: `docker compose down -v` wipes the `pgdata` volume.

---

## 5. Health Probes

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /api/v1/health/live` | ❌ | Liveness — process up (always 200) |
| `GET /api/v1/health/ready` | ❌ | Readiness — DB + Redis (200/503) |
| `GET /api/v1/health/dependencies` | ❌ | Per-dependency detail (db, redis, ai_provider, worker) |
| `GET /api/v1/system/health/live` | ✅ | Auth-bound liveness |
| `GET /api/v1/system/health/ready` | ✅ | Auth-bound readiness |
| `GET /api/v1/system/health/dependencies` | ✅ | Auth-bound dependencies |

Docker Compose healthchecks use the unauthenticated `/ready` endpoint.

---

## 6. Logs

- **Format**: JSON when `LOGGING_JSON=true`; otherwise human-readable
- **Redaction**: Central filter masks tokens, keys, secrets, PII
- **Trace IDs**: `X-Request-ID` + `X-Trace-ID` via `app/core/telemetry.py` ContextVars
- **Access**: `docker compose logs -f api` / `web`

---

## 7. Workers & Queues

- **Queue**: `workflow_queue` table (DB-as-queue)
- **Worker**: `app/workflow/worker.py` — claims `queued` executions, runs them
- **Scheduler**: `app/workflow/scheduler.py` — fires due triggers
- **Env**: `ORCHESTRATION_EXECUTE_SYNC=false` (async worker); `true` for inline tests
- **Reliability**: `IDEMPOTENCY_ENABLED`, `DLQ_ENABLED`, heartbeat (`WORKER_HEARTBEAT_INTERVAL_SECONDS=5`), staleness (`WORKER_STALE_THRESHOLD_SECONDS=120`), retries (`WORKER_MAX_RETRIES=3`)

---

## 8. Common Failures & Troubleshooting

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `database is locked` | SQLite contention under parallel workers | Use Postgres; WAL mode already set |
| `503 Service Unavailable` from `/ready` | Postgres/Redis not healthy | Check `docker compose ps`; `pg_isready` / `redis-cli ping` |
| `401 Unauthorized` on `/api/v1/*` | `AUTH_ENABLED=true` but no token | Add `Authorization: Bearer <token>`; or `AUTH_ENABLED=false` for dev |
| Migration `Target database is not up to date` | Schema drift | `alembic upgrade head` (or round-trip) |
| Web build fails | Node version / lockfile mismatch | `node -v` (expect 24); `npm ci` |
| `production_readiness` FAIL | `AUTH_ENABLED=false` or missing keys | Set `AUTH_ENABLED=true`, `JWT_SECRET_KEY`, `SECRET_ENCRYPTION_KEY` |

---

## 9. Configuration Reference

Key env vars (see `.env.example` for full list):

| Category | Vars |
|----------|------|
| Database | `DATABASE_URL`, `POSTGRES_*` |
| Redis | `REDIS_URL` |
| Auth | `AUTH_ENABLED`, `JWT_SECRET_KEY`, `SECRET_ENCRYPTION_KEY`, `ACCESS_TOKEN_LIFETIME_MINUTES` |
| Security | `SSRF_PROTECTION_ENABLED`, `PROMPT_INJECTION_PROTECTION_ENABLED`, `SECURE_AUTH_COOKIES` |
| Governance | `KILL_SWITCH_GLOBAL_PAUSE`, `APPROVAL_*`, `RESOURCE_MAX_*` |
| Feature Flags | `FEATURE_FLAGS_ENABLED`, `FEATURE_*` |
| External | `EXTERNAL_*` (timeouts, caps, SSRF, connectors) |
| Phase 12 | No dedicated env — governed by Phase 11 budgets |

---

## 10. Performance Baseline (Dev Environment)

Run from `apps/api`:

```bash
.venv/bin/python -m scripts.perf_baseline
```

Sample output (indicative, **not SLAs**):

| Operation | Median | Std Dev |
|-----------|--------|---------|
| Agent execution (single task) | ~4 ms | ± 3 ms |
| Single tool call (tool loop) | ~5 ms | ± 2 ms |
| Workflow run (1 agent step) | ~7 ms | ± 4 ms |
| Memory write 5 + search | ~2 ms | ± 1 ms |
| Simulation (14-day, 1 iter) | ~4 ms | ± 30 ms |
| Optimization (greedy, 1 var) | ~2 ms | ± 2 ms |
| Benchmark (5 cases) | ~2 ms | ± 1 ms |
| Marketplace search | ~0.2 ms | ± 1 ms |

Run on: file-backed SQLite + `MockProvider` (deterministic). Not representative of production Postgres + real LLM latency.

---

## 10b. Production Mode & Concurrent Load Baseline

Auth, rate limiting, and observability ship but are gated off by default so the
demo and test suite stay open. `scripts/run_production.sh` flips the production
chain on and verifies it over HTTP in one command:

```bash
bash scripts/run_production.sh    # from the repo root
```

It starts Postgres + Redis, migrates, seeds core company data, boots the API
with `AUTH_ENABLED=true RATE_LIMIT_ENABLED=true METRICS_ENABLED=true` and fresh
ephemeral JWT/encryption secrets, then verifies the enforced chain end-to-end:

| Check | Expect | Result |
|-------|--------|--------|
| Unauthenticated `GET /api/v1/companies` | `401 auth_required` | ✓ |
| Bootstrap-admin login | `200` + bearer token | ✓ |
| Authed `GET /api/v1/companies` | `200` | ✓ |
| Wrong password login | `403 invalid_credentials` | ✓ |
| Concurrent load baseline | ≤ 5% fatal-error rate | ✓ (0.00%) |
| `production_readiness` | PASS on identity/jwt; TLS/ingress WARN | ✓ (11 OK / 4 WARN / 1 FAIL) |

The single FAIL (`SECURE_AUTH_COOKIES` unset) is the *expected* upstream
finding: the harness runs on plain localhost without a TLS terminator. In a real
deployment set `SECURE_AUTH_COOKIES=true` behind TLS.

Concurrent load baseline (dev machine, Docker Postgres + in-process workers,
deterministic MockProvider — **not SLAs**, §42):

```bash
cd apps/api && .venv/bin/python -m scripts.load_baseline --clients 16 --requests 320
```

Measured 2026-09-14, 16 clients × 320 requests:

| Route                | Count | p50 (ms) | p95 (ms) | p99 (ms) |
|----------------------|-------|----------|----------|----------|
| agents:list          |    40 |      7.6 |     36.5 |     37.3 |
| companies:list       |   120 |      7.2 |     35.1 |     38.4 |
| health               |    40 |     24.5 |     56.0 |     58.1 |
| marketplace:agents   |    40 |      7.3 |     30.5 |     37.3 |
| metrics              |    40 |      7.4 |     37.1 |     53.1 |
| recommendations:create |    40 |    7.6 |     54.2 |     55.3 |
| **ALL**              |   320 |      7.8 |     35.6 |     55.3 |

**Throughput ≈ 1328 req/s; error rate 0.00%.** Most requests returned `401`
(deliberately unauthenticated — the baseline exercises the enforced token gate,
not authed reads); the PASS criterion is the 0.00% 5xx/network fatal rate.
Tune the mix with `--clients`/`--requests`; bounds are indicative dev-machine
measurements, not contracts.

---

## 11. Running Tests & Checks

```bash
# Backend (from apps/api)
.venv/bin/pytest -q                    # 1115 tests
.venv/bin/ruff check .                 # lint
.venv/bin/ruff format --check .        # format

# Frontend (from apps/web)
npx tsc --noEmit
npm run lint
npx vitest run
npm run build

# Full demo
bash scripts/run_demos.sh              # docker PG/Redis + 5 seeds + smoke
```

---

## 12. Production Readiness Gate

```bash
# From apps/api
.venv/bin/python -m app.checks.production_readiness
```

Exits 0 (PASS/WARN) or 1 (FAIL). Current dev config yields FAIL on:
- `AUTH_ENABLED=false`
- `JWT_SECRET_KEY` empty
- `SECRET_ENCRYPTION_KEY` empty
- `SECURE_AUTH_COOKIES=false`

Set these in production `.env` to pass.

---

## 13. References

| Doc | Scope |
|-----|-------|
| `disaster-recovery.md` | Backup/restore, RPO/RTO, procedures |
| `phase-11-production-hardening.md` | Full config inventory, gates, checklists |
| `security.md` | Threat model, controls, authZ, secrets, audit |
| `reliability.md` | Verification, recovery, evaluation, worker/queue reliability |
| `docs/demo.md` | Demo checklist + smoke path |