#!/usr/bin/env bash
# NEXUS — production-mode stack + verification harness.
#
# Brings up docker Postgres/Redis, migrates, seeds core company data, and boots
# the API with the production security chain ENABLED (auth, rate limiting,
# observability), then verifies the chain end to end over HTTP:
#   • unauth request           → 401 auth_required
#   • login (bootstrap admin)  → 200 + bearer token
#   • authed read              → 200
#   • wrong password           → 403 invalid_credentials
#   • worker drain (A2)        → queued workflow + orchestration runs reach
#     terminal state off the request path (workers enabled for the run)
#   • concurrent load baseline → p50/p95/p99 + fatal-error rate
#   • production-readiness report (expect PASS on identity/jwt with the
#     generated secrets; TLS/ingress items correctly WARN — upstream flags)
#
# The smoke runs against an ISOLATED per-run Postgres schema (created and
# dropped by this script) so a persisted bootstrap admin or stale schema from
# an earlier run can never poison the checks — the same guarantee CI's fresh-DB
# migration round trip relies on. Callers may point the smoke at their own
# database by exporting DATABASE_URL before running.
#
# Bootstrap credentials are generated fresh each run and printed to stdout —
# they are ephemeral DEV credentials, never committed, and never intended for a
# real deployment (real prod must NOT set AUTH_DEV_BOOTSTRAP_*).
#
# Usage:  bash scripts/run_production.sh
# Prereqs: apps/api/.venv, Docker daemon, curl; no API keys required (mock
# provider) unless OPENAI_API_KEY is exported by the caller.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$REPO_ROOT/apps/api"
VENV_PY="$API_DIR/.venv/bin/python"
ALEMBIC="$API_DIR/.venv/bin/alembic"
COMPOSE="docker compose -f $REPO_ROOT/docker-compose.yml"

export ENVIRONMENT="${ENVIRONMENT:-production}"
export AUTH_ENABLED=true
export RATE_LIMIT_ENABLED=true
# Cross-process rate window via the compose Redis (degrades to memory on outage).
export RATE_LIMIT_BACKEND="${RATE_LIMIT_BACKEND:-redis}"
export METRICS_ENABLED=true
# Mirror the deploy overlay (docker-compose.prod.yml) so the readiness gate is
# green: secure session cookies are the production default.
export SECURE_AUTH_COOKIES=true
# Run queues off the request path: daemon workers drain workflow + orchestration
# CREATED/QUEUED runs (see docs/operations.md §Workers & Queues).
export WORKFLOW_WORKER_ENABLED=true
export ORCHESTRATION_WORKER_ENABLED=true

# Fresh ephemeral secrets each run (keeps the smoke reproducible and key-less).
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-$(openssl rand -hex 32)}"
# Fernet-format key (cryptography's format includes the trailing '=' padding).
export SECRET_ENCRYPTION_KEY="${SECRET_ENCRYPTION_KEY:-$($VENV_PY -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")}"
export LOGGING_JSON=true
BOOTSTRAP_EMAIL="${AUTH_DEV_BOOTSTRAP_EMAIL:-admin@nexus.local}"
BOOTSTRAP_PASSWORD="$(openssl rand -hex 12)"
export AUTH_DEV_BOOTSTRAP_EMAIL="$BOOTSTRAP_EMAIL"
export AUTH_DEV_BOOTSTRAP_PASSWORD="$BOOTSTRAP_PASSWORD"

say()  { printf '\033[1;34m[prod]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[prod] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ -x "$VENV_PY" ] || die "venv not found at $API_DIR/.venv — run the api setup first"
command -v curl >/dev/null || die "curl is required"

# ── 0. Preflight ───────────────────────────────────────────────────────────
# The harness owns port 8000 for its own uvicorn. A stale stack (e.g. a dev
# `docker compose up`) would otherwise answer the checks and silently
# mis-verify. Fail fast with a hint instead.
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  die "port 8000 is in use — stop the stale stack (docker compose stop api web) and re-run"
fi

# ── 1. Infrastructure ─────────────────────────────────────────────────────
say "starting postgres + redis..."
$COMPOSE up -d postgres redis
HEALTHY=""
for _ in $(seq 1 40); do
  STATE="$($COMPOSE ps --format '{{.Name}} {{.Health}}')" || true
  PG_OK="$(printf '%s\n' "$STATE" | grep -c 'postgres.*healthy' || true)"
  REDIS_OK="$(printf '%s\n' "$STATE" | grep -c 'redis.*healthy' || true)"
  if [ "${PG_OK:-0}" -ge 1 ] && [ "${REDIS_OK:-0}" -ge 1 ]; then HEALTHY=1; break; fi
  sleep 1
done
[ -n "$HEALTHY" ] || die "postgres/redis not healthy within 40s"

# The harness owns its database: an explicit caller-provided DATABASE_URL, or a
# throwaway per-run schema. A per-run schema keeps the persistent dev DB (and
# any previously bootstrapped admin) from poisoning the smoke.
if [[ -z "${DATABASE_URL:-}" ]]; then
  SMOKE_DB="nexus_smoke_$(openssl rand -hex 4)"
  $COMPOSE exec -T postgres createdb -U nexus "$SMOKE_DB" 2>/dev/null \
    || die "could not create smoke database $SMOKE_DB (is the postgres service a superuser?)"
  export DATABASE_URL="postgresql+psycopg://nexus:nexus_dev@localhost:5433/$SMOKE_DB"
  say "smoke database: $SMOKE_DB (isolated, dropped on exit)"
fi

# ── 2. Migrations + core seed ─────────────────────────────────────────────
say "applying migrations (alembic upgrade head)..."
( cd "$API_DIR" && "$ALEMBIC" upgrade head )

say "seeding core company data (seed_company --reset)..."
( cd "$API_DIR" && "$VENV_PY" -m scripts.seed_company --reset )

# ── 3. Boot the API with the production chain on ──────────────────────────
say "starting API on 127.0.0.1:8000 (auth + rate-limit + metrics ON)..."
( cd "$API_DIR" && exec "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 ) &
API_PID=$!
cleanup() {
  kill "$API_PID" 2>/dev/null || true
  if [[ -n "${SMOKE_DB:-}" ]]; then
    # PG16 FORCE drops even with the API still draining connections.
    $COMPOSE exec -T postgres psql -U nexus -c "DROP DATABASE IF EXISTS \"$SMOKE_DB\" WITH (FORCE)" \
      >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

READY=""
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:8000/api/v1/health/ready" >/dev/null 2>&1; then READY=1; break; fi
  sleep 1
done
[ -n "$READY" ] || die "API did not become ready within 40s"

# ── 4. Verify the production chain over HTTP ──────────────────────────────
say "verifying auth chain (401 → login → authed 200 → wrong-password 403)..."
UNAUTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/companies)"
[ "$UNAUTH_CODE" = "401" ] || die "expected 401 for unauth /companies, got $UNAUTH_CODE"

LOGIN_JSON="$("$VENV_PY" - <<PY
import json, urllib.request
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/auth/login",
    data=json.dumps({"email": "$BOOTSTRAP_EMAIL", "password": "$BOOTSTRAP_PASSWORD"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        print(r.read().decode())
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()}")
    raise SystemExit(1)
PY
)"
TOKEN="$(printf '%s' "$LOGIN_JSON" | "$VENV_PY" -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
[ -n "$TOKEN" ] || die "login did not return an access token"

AUTHED_CODE="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/companies)"
[ "$AUTHED_CODE" = "200" ] || die "expected 200 for authed /companies, got $AUTHED_CODE"

BADLOGIN_CODE="$(curl -s -o /dev/null -w '%{http_code}' -H "Content-Type: application/json" \
  -d '{"email":"admin@nexus.local","password":"nope-nope-nope"}' \
  http://127.0.0.1:8000/api/v1/auth/login)"
[ "$BADLOGIN_CODE" = "403" ] || die "expected 403 invalid_credentials, got $BADLOGIN_CODE"

# ── 5. Worker drain (A2): queued work leaves the request path ─────────────
say "verifying worker drain (workflow execution + orchestration → terminal)..."
TOKEN="$TOKEN" "$VENV_PY" - <<'PY' || die "worker drain verification failed"
import json, os, time, urllib.request

BASE = "http://127.0.0.1:8000"
HDRS = {
    "Authorization": f"Bearer {os.environ['TOKEN']}",
    "Content-Type": "application/json",
}

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = dict(HDRS)
    if data is None:
        hdrs.pop("Content-Type", None)
    r = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read().decode() or "null")

ok = True
def check(label, cond):
    global ok
    print(f"    {label}: {'PASS' if cond else 'FAIL'}")
    if not cond:
        ok = False

# (a) Workflow: create definition → execute (queued, no /execute inline since
#     workflow_execute_sync=false) → worker drains QUEUED → RUNNING → terminal.
wf = req("POST", "/api/v1/workflows",
         {"name": "prod-drain-check", "description": "production harness"})
# Workflows are created in `draft`; execute only accepts active ones.
req("POST", f"/api/v1/workflows/{wf['id']}/activate")
execr = req("POST", f"/api/v1/workflows/{wf['id']}/execute", {})
status = execr["status"]
for _ in range(90):
    if status not in ("queued", "running"):
        break
    time.sleep(1)
    status = req("GET", f"/api/v1/workflows/executions/{execr['id']}")["status"]
check(f"workflow execution terminal ({status})", status == "completed")

# (b) Orchestration: POST create leaves status CREATED → worker claims it and
#     runs to a terminal status off the request path.
orch = req("POST", "/api/v1/orchestrations",
           {"objective": "verify the production worker drains a run"})
status = orch["status"]
for _ in range(90):
    if status in ("completed", "partially_completed", "failed", "cancelled"):
        break
    time.sleep(1)
    status = req("GET", f"/api/v1/orchestrations/{orch['id']}")["status"]
check(f"orchestration terminal ({status})",
      status in ("completed", "partially_completed"))

raise SystemExit(0 if ok else 1)
PY

# ── 6. Concurrent load baseline ───────────────────────────────────────────
say "running concurrent load baseline (16 clients, 320 requests)..."
( cd "$API_DIR" && "$VENV_PY" -m scripts.load_baseline --clients 16 --requests 320 \
  --base-url http://127.0.0.1:8000 ) || die "load baseline reported >5% fatal errors"

# ── 7. Production-readiness report ────────────────────────────────────────
say "production-readiness report:"
( cd "$API_DIR" && ENVIRONMENT=production "$VENV_PY" -m app.checks.production_readiness ) \
  || true

cat <<EOF

────────────────────────────────────────────────────────────────────
  NEXUS production-mode stack verified.
  • Bootstrap admin: $BOOTSTRAP_EMAIL / $BOOTSTRAP_PASSWORD
    (ephemeral, this run only — never use in real production)
  • Chain: unauth 401 ✓  login 200 ✓  authed read 200 ✓
           wrong-password 403 ✓  worker drain ✓  load baseline ✓
  • Rate limit: AUTH=20/min, DEFAULT=600/min, EXPENSIVE=30/min
    (tune via RATE_LIMIT_* env); backend=$RATE_LIMIT_BACKEND
  • Workers: workflow + orchestration daemon threads ON (drain verified)
  API:      http://127.0.0.1:8000  (docs at /docs)
  Metrics:  /api/v1/system/metrics   (bearer-token-bound)
────────────────────────────────────────────────────────────────────
EOF