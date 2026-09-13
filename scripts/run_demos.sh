#!/usr/bin/env bash
# NEXUS — deterministic full-demo runner.
#
# Brings up the docker Postgres/Redis, applies migrations, seeds all demo data
# in dependency order (--reset each time), starts a local API, and sweeps the
# Phase 11 + Phase 12 smoke suites (0×5xx). Designed for doc reviewers
# (docs/demo.md) and CI-free environments.
#
# Usage:  bash scripts/run_demos.sh
#
# Prereqs: a Python venv at apps/api/.venv and a Docker daemon running.
# The demo database is the compose local Postgres on host port 5433
# (nexus/nexus_dev/nexus) unless DATABASE_URL/AUTH_ENABLED are overridden.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$REPO_ROOT/apps/api"
VENV_PY="$API_DIR/.venv/bin/python"
ALEMBIC="$API_DIR/.venv/bin/alembic"
COMPOSE="docker compose -f $REPO_ROOT/docker-compose.yml"

# Deterministic defaults matching docker-compose.yml (envs take precedence so a
# local .env with alternate values still wins when the caller prefers).
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://nexus:nexus_dev@localhost:5433/nexus}"
export AUTH_ENABLED="${AUTH_ENABLED:-false}"

say()  { printf '\033[1;34m[demo]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[demo] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ -x "$VENV_PY" ] || die "venv not found at $API_DIR/.venv — run the api setup first"
[ -x "$ALEMBIC" ] || die "alembic not found in $API_DIR/.venv/bin"

# ── 1. Infrastructure ─────────────────────────────────────────────────────
say "starting postgres + redis containers..."
$COMPOSE up -d postgres redis

say "waiting for postgres + redis to become healthy..."
HEALTHY=""
for _ in $(seq 1 40); do
  PS_STATE="$($COMPOSE ps --format '{{.Name}} {{.Health}}')"
  PG_OK="$(printf '%s\n' "$PS_STATE" | grep -c 'postgres.*healthy')"
  REDIS_OK="$(printf '%s\n' "$PS_STATE" | grep -c 'redis.*healthy')"
  if [ "${PG_OK:-0}" -ge 1 ] && [ "${REDIS_OK:-0}" -ge 1 ]; then
    HEALTHY=1
    break
  fi
  sleep 1
done
[ -n "$HEALTHY" ] || die "postgres/redis not healthy within 40s — check: $COMPOSE ps"

# ── 2. Migrations ─────────────────────────────────────────────────────────
say "applying migrations (alembic upgrade head)..."
( cd "$API_DIR" && "$ALEMBIC" upgrade head )

# ── 3. Seed all demo data, in dependency order ────────────────────────────
SEEDS=(seed_company seed_autonomous_startup seed_external_ops \
       seed_security_governance seed_simulation_optimization)
for script in "${SEEDS[@]}"; do
  say "seeding: $script --reset"
  ( cd "$API_DIR" && "$VENV_PY" -m "scripts.$script" --reset )
done

# ── 4. Local API + smoke sweeps ───────────────────────────────────────────
say "starting the API on 127.0.0.1:8000..."
( cd "$API_DIR" && exec "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 ) &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT

say "waiting for /api/v1/health/ready..."
READY=""
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:8000/api/v1/health/ready" >/dev/null 2>&1; then
    READY=1; break
  fi
  sleep 1
done
[ -n "$READY" ] || die "API did not become ready within 40s"

say "phase 11 smoke sweep..."
( cd "$API_DIR" && "$VENV_PY" -m scripts.smoke_api --phase 11 )
say "phase 12 smoke sweep..."
( cd "$API_DIR" && "$VENV_PY" -m scripts.smoke_api --phase 12 )

# ── 5. Summary ────────────────────────────────────────────────────────────
cat <<'EOF'

────────────────────────────────────────────────────────────────────
  NEXUS demo stack is ready.
  • API:      http://127.0.0.1:8000  (docs at /docs)
  • Web:      http://localhost:3000  (docker compose up -d web)
  • Database: docker Postgres on 127.0.0.1:5433 (db "nexus")
  • Seeds:    company, autonomous startup, external ops,
              security/governance, simulation/optimization (--reset)
  • Smokes:   phase 11 ✓   phase 12 ✓   (0×5xx)
  Full reviewer's guide: docs/demo.md
────────────────────────────────────────────────────────────────────
EOF