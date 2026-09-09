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

setup_shared() {
  log "Setting up shared types package ($ROOT_DIR/packages/shared)"
  cd "$ROOT_DIR/packages/shared"
  check_cmd node
  check_cmd npm

  log "Installing shared package dependencies"
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
  --shared) setup_shared ;;
  all)
    check_cmd docker
    setup_env
    setup_backend
    setup_web
    setup_shared
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