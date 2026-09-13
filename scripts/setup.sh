#!/usr/bin/env bash
# NEXUS local development bootstrap.
# Sets up the Python backend, Node frontend, environment file, and database.
#
# Usage:
#   ./scripts/setup.sh            # full setup
#   ./scripts/setup.sh --backend  # backend only
#   ./scripts/setup.sh --web      # frontend only
#
# Prerequisites: python3, node, npm, docker (for Postgres/Redis).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"
WEB_DIR="$ROOT_DIR/apps/web"

log() { printf "\033[1;34m[NEXUS]\033[0m %s\n" "$*"; }

check_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf "Missing required tool: %s\n" "$1" >&2
    exit 1
  fi
}

setup_backend() {
  log "Setting up backend ($API_DIR)"
  cd "$API_DIR"
  check_cmd python3

  # NEXUS requires Python ≥ 3.14 (using modern type syntax, 3.14-only features).
  PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  PY_MAJOR="$(echo "$PY_VERSION" | cut -d. -f1)"
  PY_MINOR="$(echo "$PY_VERSION" | cut -d. -f2)"
  if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 14 ]; }; then
    printf "\033[1;31m[NEXUS ERROR]\033[0m Python %s detected; NEXUS requires Python >= 3.14.\n" "$PY_VERSION" >&2
    printf "  • Install Python 3.14+: https://www.python.org/downloads/\n" >&2
    printf "  • Or use the Docker path (no local Python needed):\n" >&2
    printf "      docker compose up --build\n\n" >&2
    exit 1
  fi
  log "Python $PY_VERSION ✓"

  if [ ! -d .venv ]; then
    log "Creating Python virtual environment"
    python3 -m venv .venv
  fi

  log "Installing Python dependencies"
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt -r requirements-dev.txt
  cd "$ROOT_DIR"
}

setup_web() {
  log "Setting up frontend ($WEB_DIR)"
  cd "$WEB_DIR"
  check_cmd node
  check_cmd npm

  log "Installing Node dependencies"
  npm install
  cd "$ROOT_DIR"
}

setup_env() {
  if [ -f "$ROOT_DIR/.env" ]; then
    log ".env already exists; leaving it unchanged"
  else
    log "Creating .env from .env.example"
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  fi
}

setup_stack() {
  log "Starting Postgres and Redis via Docker Compose"
  check_cmd docker
  cd "$ROOT_DIR"
  docker compose up -d postgres redis
  log "Waiting for Postgres to be ready..."
  sleep 5
}

setup_migrate() {
  log "Applying database migrations"
  cd "$API_DIR"
  source .venv/bin/activate
  alembic upgrade head
  cd "$ROOT_DIR"
}

MODE="${1:-all}"
case "$MODE" in
  --backend) setup_backend ;;
  --web) setup_web ;;
  all)
    check_cmd docker
    setup_env
    setup_backend
    setup_web
    setup_stack
    setup_migrate
    ;;
  *)
    printf "Unknown option: %s\n" "$MODE" >&2
    exit 1
    ;;
esac

log "Done."
printf "\nRun the stack with:\n\n"
printf "   docker compose up --build\n\n"
printf "Then open:\n"
printf "   Frontend:  http://localhost:3000\n"
printf "   API docs:  http://localhost:8000/docs\n\n"