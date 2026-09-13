#!/usr/bin/env bash
# NEXUS API container entrypoint.
# Applies Alembic migrations by default (opt out with AUTO_MIGRATE=false), then
# execs the container CMD (uvicorn by default).
set -euo pipefail

if [ "${AUTO_MIGRATE:-true}" != "false" ]; then
  echo "[entrypoint] applying database migrations (AUTO_MIGRATE=${AUTO_MIGRATE:-true})..."
  alembic upgrade head
  echo "[entrypoint] migrations applied."
else
  echo "[entrypoint] AUTO_MIGRATE=false — skipping migrations."
fi

exec "$@"
