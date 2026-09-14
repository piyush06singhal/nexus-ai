#!/usr/bin/env bash
# NEXUS deploy script — pulls the CI-pushed GHCR images and runs the stack in
# production mode on any Docker host (no source build needed).
#
#   bash scripts/deploy.sh [--dry-run] [--tls] [TAG] [IMAGE-REPO]
#
#   --dry-run   print what would be deployed (tag, repo, secret presence)
#               and exit without running any compose command.
#   --tls       also bring up the Caddy TLS edge (docker-compose.tls.yml) so
#               the stack is served over HTTPS. Set SITE_ADDRESS to the public
#               domain (default localhost → self-signed internal CA).
#   TAG         image tag to deploy; defaults to "latest" (CI also pushes
#               git SHA images, e.g. "49874a1" to pin an exact revision).
#   IMAGE-REPO  GHCR owner/repo; defaults to the repo of the origin git
#               remote (https://github.com/<owner>/<repo>.git) and can be
#               overridden with NEXUS_IMAGE_REPO.
#
# Secrets: real deployments export JWT_SECRET_KEY and SECRET_ENCRYPTION_KEY in
# the host environment (or a secret manager), then run this. If they are unset
# the script generates EPHEMERAL ones and warns loudly — those invalidate
# sessions on the next restart, so they are dev/bootstrap-only, never for a
# long-lived deployment. No secret is ever written to disk by this script.
set -euo pipefail

cd "$(dirname "$0")/.."

DRY_RUN=0
TLS=0
while [[ $# -gt 0 ]]; do
  case "${1}" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --tls)
      TLS=1
      shift
      ;;
    *)
      break
      ;;
  esac
done

TLS_FILES=()
if [[ "$TLS" -eq 1 ]]; then
  TLS_FILES=(-f docker-compose.tls.yml)
  # Signal the app that TLS is terminated at the Caddy edge, so the readiness
  # gate (`tls` check) passes instead of assuming plaintext transport.
  export TLS_ENABLED=true
fi

TAG="${1:-latest}"
REPO="${NEXUS_IMAGE_REPO:-${2:-}}"
if [[ -z "$REPO" ]]; then
  REMOTE="$(git config --get remote.origin.url || true)"
  REPO="$(printf '%s' "$REMOTE" | sed -E 's#.*github.com[:/]([^/:]+/[^/.]+)(\.git)?$#\1#')"
fi
if [[ -z "$REPO" ]]; then
  echo "ERROR: cannot determine the GHCR image repo — set NEXUS_IMAGE_REPO." >&2
  exit 1
fi
export NEXUS_IMAGE_REPO="$REPO" IMAGE_TAG="$TAG"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "DRY RUN — would deploy $REPO/{nexus-api,nexus-web,nexus-worker}:$TAG"
  echo "  Worker topology:                 $([[ "${API_WORKERS_ENABLED:-false}" == "true" ]] && echo "in-API (threaded)" || echo "headless 'worker' service (default)")"
  echo "  TLS edge:                        $([[ "$TLS" -eq 1 ]] && echo "enabled (SITE_ADDRESS=${SITE_ADDRESS:-localhost})" || echo "off (use --tls)")"
  echo "  JWT_SECRET_KEY set:              $([[ -n "${JWT_SECRET_KEY:-}" ]] && echo yes || echo no)"
  echo "  SECRET_ENCRYPTION_KEY set:       $([[ -n "${SECRET_ENCRYPTION_KEY:-}" ]] && echo yes || echo no)"
  echo "  (no compose commands executed)"
  exit 0
fi

if [[ -z "${JWT_SECRET_KEY:-}" || -z "${SECRET_ENCRYPTION_KEY:-}" ]]; then
  echo "WARNING: JWT_SECRET_KEY / SECRET_ENCRYPTION_KEY unset — generating EPHEMERAL keys." >&2
  echo "         Sessions will be invalidated on the next restart. Use a secret manager in production." >&2
  export JWT_SECRET_KEY="$(openssl rand -hex 32)"
  export SECRET_ENCRYPTION_KEY="$(
    { python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())' \
        || openssl rand -base64 32; } 2>/dev/null | tr -d '\n'
  )"
fi

echo "==> Deploying $REPO/{nexus-api,nexus-web}:$TAG (production mode, split worker)"
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull api web worker
docker compose -f docker-compose.yml -f docker-compose.prod.yml "${TLS_FILES[@]}" up -d

echo "==> Waiting for the API and worker to become healthy..."
for i in $(seq 1 30); do
  status="$(docker compose -f docker-compose.yml -f docker-compose.prod.yml "${TLS_FILES[@]}" ps --format json api 2>/dev/null || true)"
  if printf '%s' "$status" | grep -q 'healthy'; then
    echo "==> API healthy."
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    echo "ERROR: API not healthy after 30×5s. Inspect: docker compose ps / docker compose logs api." >&2
    exit 1
  fi
  sleep 5
done

# The worker container liveness is its heartbeat healthcheck; wait for it too
# so deploy completes only once BOTH request-serving and queue-consumer paths
# are up (set API_WORKERS_ENABLED=true to skip — API then runs workers in-process).
if [[ "${API_WORKERS_ENABLED:-false}" != "true" ]]; then
  for i in $(seq 1 30); do
    status="$(docker compose -f docker-compose.yml -f docker-compose.prod.yml "${TLS_FILES[@]}" ps --format json worker 2>/dev/null || true)"
    if printf '%s' "$status" | grep -q 'healthy'; then
      echo "==> Worker healthy (headless queue consumers running)."
      break
    fi
    if [[ "$i" -eq 30 ]]; then
      echo "WARNING: worker not healthy after 30×5s. Inspect: docker compose logs worker." >&2
      break
    fi
    sleep 5
  done
fi

echo
echo "NEXUS deployed (production mode):"
if [[ "$TLS" -eq 1 ]]; then
  echo "  Edge: https://${SITE_ADDRESS:-localhost}  (Caddy, Caddyfile: infrastructure/caddy/Caddyfile)"
else
  echo "  API:  http://localhost:8000/docs"
  echo "  Web:  http://localhost:3000"
fi
echo "  Tags: $REPO/{nexus-api,nexus-web,nexus-worker}:$TAG"
echo
echo "Note: this boots a single Docker host. Horizontal replication, managed"
echo "Postgres, TLS and failover are deployment concerns (see docs/operations.md)."