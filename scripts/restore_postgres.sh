#!/usr/bin/env bash
# Restore a NEXUS Postgres backup into the target database.
#
#   bash scripts/restore_postgres.sh --list <BACKUP_FILE>    # inspect only
#   bash scripts/restore_postgres.sh --dry-run <BACKUP_FILE> # validate, no changes
#   bash scripts/restore_postgres.sh --latest                # restore most recent backup
#   bash scripts/restore_postgres.sh <BACKUP_FILE>
#
# Defaults target the dev compose Postgres on localhost:5433. Override via
# POSTGRES_HOST/PORT/USER/DB or set DATABASE_URL for the full connection string.
# Client resolution mirrors backup_postgres.sh: host binary first, then the
# compose postgres container (which reaches the DB on its own port 5432 and
# needs the backup copied in via docker cp).
#
# ⚠️  WARNING: restore DROPS and recreates the target database.
#           Always validate with --list / --dry-run against a scratch DB first.
set -euo pipefail

cd "$(dirname "$0")/.."

LIST=0
DRY_RUN=0
LATEST=0
FILE=""

while [[ $# -gt 0 ]]; do
  case "${1}" in
    --list)    LIST=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --latest)  LATEST=1; shift ;;
    *)         FILE="$1"; shift ;;
  esac
done

PG_HOST="${POSTGRES_HOST:-localhost}"
PG_PORT="${POSTGRES_PORT:-5433}"          # host-facing port
PG_USER="${POSTGRES_USER:-nexus}"
PG_DB="${POSTGRES_DB:-nexus}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

if [[ "$LATEST" -eq 1 ]]; then
  FILE=$(ls -t "${BACKUP_DIR}/${PG_DB}_"*.dump 2>/dev/null | head -1)
  if [[ -z "$FILE" ]]; then
    echo "ERROR: no backups found in $BACKUP_DIR" >&2
    exit 1
  fi
  echo "==> Using latest backup: $FILE"
fi

if [[ -z "$FILE" ]]; then
  echo "Usage: $0 [--list|--dry-run] [--latest] <BACKUP_FILE>" >&2
  exit 1
fi
if [[ ! -f "$FILE" ]]; then
  echo "ERROR: backup file not found: $FILE" >&2
  exit 1
fi

# Resolve postgres client commands: host binary -> env override -> docker exec.
# When docker exec is used all clients reach the DB on the CONTAINER's own port
# (5432) and backups must be copied in/out via docker cp.
PG_DEBUG_CONTAINER=""
PG_DEBUG_DPORT=""
if [[ -n "${PG_RESTORE:-}" ]]; then
  PG_RESTORE_CMD="$PG_RESTORE"
elif command -v pg_restore >/dev/null 2>&1; then
  PG_RESTORE_CMD="pg_restore"
else
  PG_DEBUG_CONTAINER="$(docker compose ps -q postgres 2>/dev/null | head -1 || true)"
  if [[ -z "$PG_DEBUG_CONTAINER" ]]; then
    echo "ERROR: pg_restore not found on PATH and no compose postgres container to exec into." >&2
    echo "       Install postgresql-client or start the stack." >&2
    exit 1
  fi
  PG_DEBUG_DPORT="${PG_DEBUG_DPORT:-5432}"
  PG_RESTORE_CMD="docker exec $PG_DEBUG_CONTAINER pg_restore"
fi

# The other clients (psql/dropdb/createdb) live alongside pg_restore; when in
# docker mode treat them as container commands too.
if [[ -n "$PG_DEBUG_CONTAINER" ]]; then
  PSQL_CMD="docker exec $PG_DEBUG_CONTAINER psql"
  PGDROP_CMD="docker exec $PG_DEBUG_CONTAINER dropdb"
  PGCREATE_CMD="docker exec $PG_DEBUG_CONTAINER createdb"
else
  PSQL_CMD="${PSQL_CMD:-psql}"
  PGDROP_CMD="${PGDROP_CMD:-dropdb}"
  PGCREATE_CMD="${PGCREATE_CMD:-createdb}"
fi
export PGPASSWORD="$POSTGRES_PASSWORD"

# Connection args depend on WHERE the client runs (host network vs container).
CONN_ARGS=""
if [[ -n "$PG_DEBUG_CONTAINER" ]]; then
  CONN_ARGS="-h localhost -p $PG_DEBUG_DPORT"
else
  CONN_ARGS="-h $PG_HOST -p $PG_PORT"
fi

if [[ "$LIST" -eq 1 ]]; then
  echo "==> Contents of $FILE:"
  if [[ -n "$PG_DEBUG_CONTAINER" ]]; then
    local_tmp="/tmp/nexus_restore_list.dump"
    docker cp "$FILE" "${PG_DEBUG_CONTAINER}:${local_tmp}"
    $PG_RESTORE_CMD --list "$local_tmp" | head -25
    docker exec "$PG_DEBUG_CONTAINER" rm -f "$local_tmp"
  else
    $PG_RESTORE_CMD --list "$FILE" | head -25
  fi
  exit 0
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "DRY RUN — would restore $FILE"
  echo "  Target: ${PG_HOST}:${PG_PORT}/${PG_DB}  (container: $PG_DEBUG_CONTAINER)"
  echo "  Restore client: $PG_RESTORE_CMD"
  echo "  (no destructive commands executed)"
  exit 0
fi

echo "==> Restoring $FILE — ${PG_HOST}:${PG_PORT}/${PG_DB}"
echo "    ⚠️   Dropping and recreating database..."
$PGDROP_CMD $CONN_ARGS -U "$PG_USER" --if-exists "$PG_DB" 2>/dev/null || true
$PGCREATE_CMD $CONN_ARGS -U "$PG_USER" "$PG_DB"

if [[ -n "$PG_DEBUG_CONTAINER" ]]; then
  local_tmp="/tmp/nexus_restore_$(basename "$FILE")"
  docker cp "$FILE" "${PG_DEBUG_CONTAINER}:${local_tmp}"
  # shellcheck disable=SC2086
  $PG_RESTORE_CMD $CONN_ARGS -U "$PG_USER" -d "$PG_DB" --no-owner --no-privileges --if-exists --clean "$local_tmp"
  docker exec "$PG_DEBUG_CONTAINER" rm -f "$local_tmp"
else
  # shellcheck disable=SC2086
  $PG_RESTORE_CMD $CONN_ARGS -U "$PG_USER" -d "$PG_DB" --no-owner --no-privileges --if-exists --clean "$FILE"
fi
echo "==> Restore complete."
echo "==> Verifying tables:"
# shellcheck disable=SC2086
$PSQL_CMD $CONN_ARGS -U "$PG_USER" -d "$PG_DB" -c '\dt' 2>/dev/null | head -20