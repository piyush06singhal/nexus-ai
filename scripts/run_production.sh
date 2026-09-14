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
#   • concurrent load baseline → p50/p95/p99 + fatal-error rate
#   • production-readiness report (expect PASS on identity/jwt with the
#     generated secrets; TLS/ingress items correctly WARN — upstream flags)
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

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://nexus:nexus_dev@localhost:5433/nexus}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export AUTH_ENABLED=true
export RATE_LIMIT_ENABLED=true
export METRICS_ENABLED=true

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

# ── 2. Migrations + core seed ─────────────────────────────────────────────
say "applying migrations (alembic upgrade head)..."
( cd "$API_DIR" && "$ALEMBIC" upgrade head )

say "seeding core company data (seed_company --reset)..."
( cd "$API_DIR" && "$VENV_PY" -m scripts.seed_company --reset )

# ── 3. Boot the API with the production chain on ──────────────────────────
say "starting API on 127.0.0.1:8000 (auth + rate-limit + metrics ON)..."
( cd "$API_DIR" && exec "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 ) &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT

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

# ── 5. Concurrent load baseline ───────────────────────────────────────────
say "running concurrent load baseline (16 clients, 320 requests)..."
( cd "$API_DIR" && "$VENV_PY" -m scripts.load_baseline --clients 16 --requests 320 \
  --base-url http://127.0.0.1:8000 ) || die "load baseline reported >5% fatal errors"

# ── 6. Production-readiness report ────────────────────────────────────────
say "production-readiness report:"
( cd "$API_DIR" && ENVIRONMENT=production "$VENV_PY" -m app.checks.production_readiness ) \
  || true

cat <<EOF

────────────────────────────────────────────────────────────────────
  NEXUS production-mode stack verified.
  • Bootstrap admin: $BOOTSTRAP_EMAIL / $BOOTSTRAP_PASSWORD
    (ephemeral, this run only — never use in real production)
  • Chain: unauth 401 ✓  login 200 ✓  authed read 200 ✓
           wrong-password 403 ✓  load baseline ✓
  • Rate limit: AUTH=20/min, DEFAULT=600/min, EXPENSIVE=30/min
    (tune via RATE_LIMIT_* env)
  API:      http://127.0.0.1:8000  (docs at /docs)
  Metrics:  /api/v1/system/metrics   (bearer-token-bound)
────────────────────────────────────────────────────────────────────
EOF