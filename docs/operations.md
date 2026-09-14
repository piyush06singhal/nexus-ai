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

- Alembic head: `0015_pgvector` (adds the pgvector semantic-memory column; see *pgvector semantic memory* §Migration below)
- Env-driven: `alembic/env.py` reads `settings.database_url` from `DATABASE_URL`
- Round-trip tested in CI: `upgrade head` → `downgrade base` → `upgrade head`
- PostgreSQL-only revisions: `0015_pgvector` runs `CREATE EXTENSION vector` + adds `memories.embedding_vector vector(1536)` (+ HNSW index) **only on the `postgresql` dialect** — it is a no-op on SQLite, so `alembic upgrade head` on SQLite (tests/dev) stays green. The dev/CI Postgres uses the `pgvector/pgvector` Docker image so the extension is present.
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
| **Automated** | Hourly snapshot via `scripts/backup_postgres.sh` + cron (below) |

Local dev: `docker compose down -v` wipes the `pgdata` volume.

### Backup / restore scripts

Both scripts auto-detect the postgres client — a host `pg_dump`/`pg_restore` if
installed, otherwise they `docker exec` into the compose postgres container
(which ships the tools) and copy artifacts out/in with `docker cp`. No postgres
client install is required on the deploy host.

```bash
# Backup (defaults: localhost:5433, user/db nexus; retention 7 days)
bash scripts/backup_postgres.sh [--dry-run]
#  → ./backups/nexus_<timestamp>.dump ; old dumps > RETENTION_DAYS pruned

# Inspect / validate a backup (no destructive action)
bash scripts/restore_postgres.sh --list <backup.dump>
bash scripts/restore_postgres.sh --dry-run <backup.dump>

# Restore (⚠️ DROPS and recreates the target database!)
bash scripts/restore_postgres.sh <backup.dump>      # latest: --latest
```

Common overrides (env): `POSTGRES_HOST/PORT/USER/DB`, `BACKUP_DIR`,
`RETENTION_DAYS`, `DATABASE_URL`. Without password auth on a remote host,
export `POSTGRES_PASSWORD` (never commit it).

**RPO schedule (crond):** an an hourly dump bounds RPO without PITR at ≤ 1 h.

```cron
# every day at 02:17 ... or hourly:
17 * * * *  cd /path/to/nexus-ai && bash scripts/backup_postgres.sh >> /var/log/nexus-backup.log 2>&1
```

**Verify every backup** by `--list`-ing it or restoring to a scratch DB — a
backup that has never been restored is a hope, not a backup.

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
- **Env**: `WORKFLOW_WORKER_ENABLED` / `ORCHESTRATION_WORKER_ENABLED` (daemon worker
  threads; `true` in production mode), `ORCHESTRATION_EXECUTE_SYNC=false` (async);
  `true` for inline tests
- **Reliability**: `IDEMPOTENCY_ENABLED`, `DLQ_ENABLED`, heartbeat (`WORKER_HEARTBEAT_INTERVAL_SECONDS=5`), staleness (`WORKER_STALE_THRESHOLD_SECONDS=120`), retries (`WORKER_MAX_RETRIES=3`)

### Two worker topologies (Item 6)

Worker startup is shared between the API process and a headless entrypoint via
`app/workers.py::start_workers()/stop_workers()`, so the same daemons run in
either topology:

1. **In-process (default, dev/CI)**: the FastAPI lifespan starts the daemon
   threads when the `*_WORKER_ENABLED` flags are set. `run_production.sh` and
   the single-container compose stack use this.
2. **Split container (production)**: `docker-compose.prod.yml` runs a dedicated
   `worker` service using `python -m app.main_worker` from the same API image.
   The API container runs worker-free (`WORKFLOW_WORKER_ENABLED=false`) and
   only serves requests; the worker owns the queues. Scale out with an extra
   `docker compose up -d --scale worker=N` (claims are atomic). Set
   `API_WORKERS_ENABLED=true` to fall back to the single-container topology.

The headless worker refreshes a heartbeat file (`WORKER_HEARTBEAT_PATH`, set to
`/tmp/nexus-worker.heartbeat` in the overlay) each poll; its compose healthcheck
fails if the file goes stale, so a hung/dead worker is detected. `scripts/deploy.sh`
waits for both API and worker to be healthy before completing.

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
| Feature Flags | `FEATURE_FLAGS_ENABLED`, `FEATURE_*` |
| Rate limiting | `RATE_LIMIT_ENABLED`, `RATE_LIMIT_BACKEND` (`memory` per-process, `redis` cross-process ZSET — degrades to memory on outage), `RATE_LIMIT_*_PER_MINUTE` |
| Workers | `WORKFLOW_WORKER_ENABLED`, `ORCHESTRATION_WORKER_ENABLED`, `ORCHESTRATION_*`, `WORKER_HEARTBEAT_PATH` (headless-worker heartbeat file), `API_WORKERS_ENABLED` (compose: in-API vs split) |
| Governance | `KILL_SWITCH_GLOBAL_PAUSE`, `APPROVAL_*`, `RESOURCE_MAX_*`, `RESOURCE_LIMITS_PROVISION` (seed per-tenant limits at startup), `RESOURCE_MAX_PHASE12_DEFAULT` (shared per-day cap for the 8 Phase 12 categories) |
| Startup AI | `MODEL_PLANNERS_ENABLED` (mission analysis + strategy via real model when a key exists; else deterministic) |
| Monitoring | `PROMETHEUS_RETENTION`, `GRAFANA_ADMIN_USER/PASSWORD`, `PROMETHEUS_PORT`, `GRAFANA_PORT` |
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
| Worker drain — workflow execution → terminal | `completed` (worker daemon) | ✓ |
| Worker drain — orchestration run → terminal | `completed` (worker daemon) | ✓ |
| Concurrent load baseline | ≤ 5% fatal-error rate | ✓ (0.00%) |
| `production_readiness` | PASS on identity/jwt + governance; TLS/ingress + sandboxing WARN | ✓ (15 OK / 2 WARN / 0 FAIL) |

The remaining WARN items are honest deployment-context flags, not code gaps:
`tls` warns only because this run is plaintext (a `--tls` deploy exports
`TLS_ENABLED=true` and PASSes), and `os_sandboxing` warns because OS-level
process isolation cannot be fabricated in-process without new dependencies
(tool calls are still bounded in-process — timeout, memory, output-size caps
and fs/network/process allow flags). `RESOURCE_LIMITS_PROVISION=true` (set by
the harness) turns both resource-limit checks green, seeding the 5 core + 8
Phase 12 categories as global + per-tenant defaults. `SECURE_AUTH_COOKIES=true`
is set by the harness so the session-cookie check is green (the deploy overlay
defaults it too).

The harness runs against an **isolated per-run Postgres schema** (created and
dropped per run) so a stale bootstrap admin or schema from a previous run can
never poison the checks; export `DATABASE_URL` to point the smoke at your own
database instead.

Concurrent load baseline (dev machine, Docker Postgres + Redis-backed rate
limiter + in-process workers, deterministic MockProvider — **not SLAs**, §42):

```bash
cd apps/api && .venv/bin/python -m scripts.load_baseline --clients 16 --requests 320
```

Measured 2026-09-14, 16 clients × 320 requests (RATE_LIMIT_BACKEND=redis):

| Route                | Count | p50 (ms) | p95 (ms) | p99 (ms) |
|----------------------|-------|----------|----------|----------|
| agents:list          |    40 |     10.3 |     21.7 |     29.2 |
| companies:list       |   120 |     11.3 |     21.9 |     43.9 |
| health               |    40 |     45.9 |     68.6 |     91.5 |
| marketplace:agents   |    40 |     11.6 |     25.7 |     41.7 |
| metrics              |    40 |     12.6 |     43.4 |     44.2 |
| recommendations:create |    40 |    12.7 |     31.7 |     44.8 |
| **ALL**              |   320 |     12.7 |     47.0 |     57.9 |

**Throughput ≈ 915 req/s; error rate 0.00%.** Most requests returned `401`
(deliberately unauthenticated — the baseline exercises the enforced token gate,
not authed reads); the PASS criterion is the 0.00% 5xx/network fatal rate.
Tune the mix with `--clients`/`--requests`; bounds are indicative dev-machine
measurements, not contracts.

---

## 11. Deployment

Three-part path: **CI pushes GHCR images → `scripts/deploy.sh` runs them on any
Docker host → a managed platform is the documented (not shipped) long-term path.**

### 11a. GHCR image push (CI)

`.github/workflows/ci.yml` adds a `docker-push` job after the backend/frontend/`docker`
builds. It runs **only on pushes to `main`** (never on pull requests, so forks can't
trigger it) and needs the `packages: write` permission on the GitHub repo.

It builds and pushes two images per commit, tagged `:<sha>` and `:latest`:

| Image          | Tag pattern                                             |
|----------------|---------------------------------------------------------|
| `nexus-api`    | `ghcr.io/<owner>/<repo>/nexus-api:<sha>` + `:latest`    |
| `nexus-web`    | `ghcr.io/<owner>/<repo>/nexus-web:<sha>` + `:latest`    |

Login uses `GITHUB_TOKEN` by default; a repo may set `GHCR_TOKEN` to use a
dedicated registry credential. `--cache-from/to: type=gha` reuses the GitHub
Actions cache across runs.

### 11b. `scripts/deploy.sh` — one-command deploy

On any Docker host with the repo checked out (no source build needed):

```bash
bash scripts/deploy.sh [--dry-run] [TAG] [IMAGE-REPO]
```

- `--dry-run` prints what would be deployed (tag, repo, whether the two secret
  keys are present) and exits without touching Docker.
- `TAG` defaults to `latest`; pass a git SHA (e.g. `49874a1`) to pin an exact
  revision.
- `IMAGE-REPO` defaults to the repo of the `origin` git remote
  (`github.com/<owner>/<repo>.git`) and can be overridden with `NEXUS_IMAGE_REPO`.

The script:

1. Requires `JWT_SECRET_KEY` and `SECRET_ENCRYPTION_KEY`. If either is unset it
   generates **ephemeral** ones and warns loudly — those invalidate sessions on
   the next restart, so real deployments set them from a secret manager
   (nothing is ever written to disk by the script).
2. `docker compose -f docker-compose.yml -f docker-compose.prod.yml pull api web worker`
3. `docker compose ... up -d` — boots the prod overlay (below). With
   `--tls`, `docker-compose.tls.yml` is layered on for the Caddy HTTPS edge.
4. Polls the API container healthcheck and the worker heartbeat healthcheck
   (30 × 5 s each) and fails with a hint if either never turns healthy.

### 11c. `docker-compose.prod.yml` — production overlay

Overlay on the base `docker-compose.yml`:

- **Prebuilt images, no build**: `build: !reset null` clears the base `build:`
  keys and swaps in the pulled GHCR images (`NEXUS_IMAGE_REPO`/`IMAGE_TAG`
  template vars, both defaulting for a local `.env`).
- **Split worker topology**: the `api` service serves requests worker-free
  (worker flags default `false`, overridable with `API_WORKERS_ENABLED=true`),
  and a dedicated `worker` service runs `python -m app.main_worker` with both
  worker flags `true`, its own DB/Redis URLs, a heartbeat-file healthcheck, and
  `AUTO_MIGRATE=false` (the API already applied migrations). See §7.
- **Hardened chain on by default**: `AUTH_ENABLED=true`,
  `RATE_LIMIT_ENABLED=true`, `RATE_LIMIT_BACKEND=redis`,
  `LOGGING_JSON=true`, `SECURE_AUTH_COOKIES=true`.
- **Mandatory secrets**: `${JWT_SECRET_KEY:?}` / `${SECRET_ENCRYPTION_KEY:?}`
  make compose fail fast until real keys are exported.
- **Optional model keys**: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` pass through
  to both api and worker; leave unset for keyless deterministic mode.
- **Pinned CORS** to the real frontend origin (`CORS_ORIGINS`), overriding the
  dev default.
- Postgres/Redis URLs, ports, healthchecks and `depends_on` are **inherited
  unchanged** from the base file.

### 11d. TLS edge (Caddy)

`docker-compose.tls.yml` layers a Caddy v2 reverse proxy (external `80`/`443`)
in front of the stack — `/api/*`, `/docs`, `/redoc`, `/openapi.json` → api;
everything else → web. Automatic HTTPS: public domains via Let's Encrypt, an
internal self-signed CA for `localhost`. `SITE_ADDRESS` names the host; the
overlay hardens cookies (`SECURE_AUTH_COOKIES`) and pins `CORS_ORIGINS` /
`TRUSTED_HOSTS` to it. `scripts/deploy.sh --tls` also exports `TLS_ENABLED=true`
so the readiness `tls` gate reports PASS (TLS terminated at this edge) instead
of warning about plaintext. Without the Caddy edge, set `TLS_ENABLED=true`
yourself whenever an upstream LB/pass provides TLS.

### 11e. Managed deployment path (documented, not shipped)

For horizontal replication, TLS termination, managed Postgres with PITR and
auto-failover, the documented targets are a PaaS in the Fly.io/render family or
a managed Postgres provider. **No such config files are shipped in this repo** —
they are per-account files that encode an account token / platform-specific
settings, so generating them is the deployer's step, from the base image + the
production env above. See §4 (backups) and §13 (readiness gate) for what those
runs inherit.

---

## 11f. Monitoring & Alerting (Item 5)

`docker-compose.monitoring.yml` layers Prometheus + Grafana over the stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
# Prometheus: http://localhost:9090   Grafana: http://localhost:3001
# Grafana default login admin/admin — change immediately (GF_SECURITY_ADMIN_*).
```

- **Metrics** are exposed at `/api/v1/system/metrics/prometheus` in Prometheus
  text exposition format (counters `*_total`, gauges, histograms
  `*_milliseconds_count/_sum`). The path is auth-exempt so the scraper needs no
  credentials; it carries process-level data only — no per-tenant rows.
- **Prometheus** scrapes the API every 15 s (config:
  `infrastructure/prometheus/prometheus.yml`), retention via
  `PROMETHEUS_RETENTION` (default 15 d).
- **Grafana** ships a prebuilt NEXUS dashboard (`infrastructure/grafana`,
  provisioned datasource + file provider): request rate, error rate, avg
  latency, queue depth, token usage, process uptime.
- **Alerting**: wire Prometheus `alerting` rules to your Alertmanager/notification
  channel — the natural first rules are `request_error_total` rate > 0 sustained
  and `nexus_process_started_at` churn (unexpected restarts).

---

## 12. Running Tests & Checks

```bash
# Backend (from apps/api)
.venv/bin/pytest -q                    # 1182 tests + 3 keyless/pgvector skips (skips resolved on a live Postgres)
.venv/bin/ruff check .                 # lint
.venv/bin/ruff format --check .        # format

# pgvector semantic-memory test (PostgreSQL only; skipped on SQLite)
PGVECTOR_TEST_DATABASE_URL='postgresql+psycopg://nexus:nexus_dev@localhost:5433/nexus' \
  .venv/bin/pytest tests/test_pgvector.py

# Frontend (from apps/web)
npx tsc --noEmit
npm run lint
npx vitest run
npm run build

# Full demo
bash scripts/run_demos.sh              # docker PG/Redis + 5 seeds + smoke
```

---

## 13. Production Readiness Gate

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

## 14. References

| Doc | Scope |
|-----|-------|
| `disaster-recovery.md` | Backup/restore, RPO/RTO, procedures |
| `phase-11-production-hardening.md` | Full config inventory, gates, checklists |
| `security.md` | Threat model, controls, authZ, secrets, audit |
| `reliability.md` | Verification, recovery, evaluation, worker/queue reliability |
| `docs/demo.md` | Demo checklist + smoke path |