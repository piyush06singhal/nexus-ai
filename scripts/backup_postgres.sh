#!/usr/bin/env bash
# Automated Postgres backup with configurable retention.
#
#   bash scripts/backup_postgres.sh [--dry-run]
#
# Defaults match the dev compose stack (port 5433, user/db nexus). Override via
# environment or export a real DATABASE_URL for the full connection string.
# Backups land in $BACKUP_DIR (default ./backups) as a timestamped .dump file.
# Old backups older than $RETENTION_DAYS (default 7) are pruned automatically.
#
# Client resolution: prefers a host `pg_dump` binary if present; otherwise runs
# pg_dump inside the compose postgres container (that is where the pgvector
# image ships the tools) and copies the artifact out with `docker cp`.
# Override explicitly with PG_DUMP (a command prefix).
#
# Secrets: POSTGRES_PASSWORD (or DATABASE_URL) supplies DB credentials.
# No secret is ever written to disk or logged.
set -euo pipefail

cd "$(dirname "$0")/.."

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

PG_HOST="${POSTGRES_HOST:-localhost}"
PG_PORT="${POSTGRES_PORT:-5433}"          # host-facing port
PG_USER="${POSTGRES_USER:-nexus}"
PG_DB="${POSTGRES_DB:-nexus}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="${BACKUP_DIR}/${PG_DB}_${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

# Resolve how to invoke pg_dump: host binary -> env override -> docker exec.
# When docker exec is used the caller must reach the DB on the CONTAINER's own
# port (5432), not the host-mapped port, and copy the artifact out with docker
# cp — both handled via PG_DEBUG_CONTAINER / PG_DEBUG_DPORT below.
PG_DEBUG_CONTAINER=""
PG_DEBUG_DPORT=""
if [[ -n "${PG_DUMP:-}" ]]; then
  CLIENT="$PG_DUMP"
elif command -v pg_dump >/dev/null 2>&1; then
  CLIENT="pg_dump"
else
  PG_DEBUG_CONTAINER="$(docker compose ps -q postgres 2>/dev/null | head -1 || true)"
  if [[ -z "$PG_DEBUG_CONTAINER" ]]; then
    echo "ERROR: pg_dump not found on PATH and no compose postgres container to exec into." >&2
    echo "       Install postgresql-client (includes pg_dump) or start the stack." >&2
    exit 1
  fi
  PG_DEBUG_DPORT="${PG_DEBUG_DPORT:-5432}"  # container-internal port remains 5432
  CLIENT="docker exec $PG_DEBUG_CONTAINER pg_dump"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "DRY RUN — would back up $PG_DB → $FILE"
  echo "  Retention: ${RETENTION_DAYS}d"
  echo "  Backups in: $BACKUP_DIR"
  echo "  Client: $CLIENT${PG_DEBUG_CONTAINER:+ (docker exec: $PG_DEBUG_CONTAINER)}"
  echo "  (no commands executed)"
  exit 0
fi

# Connection args depend on WHERE pg_dump runs (host network vs container net).
CONN_ARGS=""
if [[ -n "$PG_DEBUG_CONTAINER" ]]; then
  CONN_ARGS="-h localhost -p $PG_DEBUG_DPORT"
else
  CONN_ARGS="-h $PG_HOST -p $PG_PORT"
fi

export PGPASSWORD="$POSTGRES_PASSWORD"

echo "==> Backing up $PG_DB → $FILE"
if [[ -n "$PG_DEBUG_CONTAINER" ]]; then
  # Write inside the container (which has no mounted backup dir), then copy out.
  IN_TMP="/tmp/nexus_backup_${TIMESTAMP}.dump"
  $CLIENT $CONN_ARGS -U "$PG_USER" -d "$PG_DB" -Fc -f "$IN_TMP"
  docker cp "${PG_DEBUG_CONTAINER}:${IN_TMP}" "$FILE"
  docker exec "$PG_DEBUG_CONTAINER" rm -f "$IN_TMP"
else
  $CLIENT $CONN_ARGS -U "$PG_USER" -d "$PG_DB" -Fc -f "$FILE"
fi
echo "==> Backup complete: $(du -h "$FILE" | cut -f1) ($FILE)"

# Prune old backups
if [[ "$RETENTION_DAYS" -gt 0 ]]; then
  PRUNED=$(find "$BACKUP_DIR" -name "${PG_DB}_*.dump" -type f -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)
  if [[ "$PRUNED" -gt 0 ]]; then
    echo "==> Pruned $PRUNED backup(s) older than ${RETENTION_DAYS} days"
  fi
fi

echo "==> Current backups:"
ls -lh "$BACKUP_DIR"/*.dump 2>/dev/null || echo "  (none)"