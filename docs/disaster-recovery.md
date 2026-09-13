# NEXUS — Disaster Recovery

Operational DR plan for the NEXUS platform: what to back up, when, how to
restore, and how to verify recovery — including the Phase 11 guarantees
(append-only audit, circuit breakers, dead-letter queue, health probes).

Honest scope: this is a *procedural* runbook for the current single-Postgres
architecture (the deploy target). Multi-region/ZK/Kubernetes DR is a documented
deployment item, not claimed.

---

## 1. Data inventory

| Store | Backend | Back up? | RPO target | Notes |
|---|---|---|---|---|
| `app` DB (all Phase 0–11 tables) | Postgres (port 5433) | **Yes, primary** | ≤ 15 min | Includes `audit_events` (append-only), `security_events`, secrets ciphertext |
| Redis | Redis (6379) | Regenerable | — | Cache/queue only; rebuild from DB |
| Model/execution artifacts | inside `app` DB | Yes (rows) | ≤ 15 min | `agent_executions`, `tool_calls` |
| Browser/computer observations | inside `app` DB | Yes (rows) | ≤ 15 min | `browser_*`, `computer_*` |
| Logs / metrics | file/stdout + `system_health_records` in DB | Logs optional | — | Not a source of truth |

Secrets are encrypted at rest (Fernet key from env) — backing up the DB is safe
and does **not** expose plaintext; restoring requires the same
`SECRET_ENCRYPTION_KEY` (keep it in the secret manager / password store).

---

## 2. Backup procedure

Recommended (operators): continuous WAL archiving + nightly full backups.

```bash
# Postgres (docker-compose maps host 5433)
pg_dump -h localhost -p 5433 -U nexus -d nexus -Fc -f nexus-$(date +%F).dump
# restore dry-run
pg_restore --list nexus-$(date +%F).dump | head
```

For the SQLite dev/demo path (same schema):

```bash
cp /tmp/nexus_secdemo.db /tmp/nexus_secdemo.db.bak
```

**Verify every backup** by restoring to a scratch DB (see §4). A backup that has
never been restored is a hope, not a backup.

---

## 3. RPO / RTO

- **RPO**: ≤ 15 min with WAL archiving; a full nightly dump alone gives ≤ 24 h.
- **RTO targets**: DB restore ≤ 30 min; full stack restart ≤ 15 min;
  fully verified recovery internal target 4 h.

---

## 4. Restore procedure (drill)

```bash
# 1. Stand up a fresh Postgres
docker compose up -d postgres

# 2. Create the empty target
psql -h localhost -p 5433 -U nexus -d nexus -c "SELECT count(*) FROM audit_events;"

# 3. Restore the dump (fresh DB, or drop/rebuild a scratch one)
pg_restore -h localhost -p 5433 -U nexus -d nexus --clean --if-exists nexus-$(date +%F).dump

# 4. Apply Alembic to bring any migrations after the dump's point
cd apps/api && .venv/bin/alembic upgrade head

# 5. Verify — the audit chain and a few tables
psql ... -c "SELECT seq, action, hash FROM audit_events ORDER BY seq DESC LIMIT 5;"
```

Then run the **recovery verification** (see below).

### Recovery drill — automated checks

| Check | How | Pass condition |
|---|---|---|
| Audit chain intact | `GET /api/v1/security/audit/verify` or seed script | `INTACT` |
| Health probes | `GET /api/v1/system/health/live`, `/ready`, `/dependencies` | all `healthy` |
| Queue drains | run the worker, list `workflow_queue` pending → 0 | drained |
| Dead-letter present | `dead_letter_jobs` table counts match pre-backup | reconciled |
| Secrets decrypt | `SecretManager.retrieve` on a test secret | decrypts (key matched) |

`python -m scripts.seed_security_governance --reset` doubles as a smoke drill:
it verifies the hash chain and exercises every subsystem the restore touches.

---

## 5. Failure modes & recovery paths

| Failure | Detection | Recovery |
|---|---|---|
| **Postgres down** | `/health/dependencies` red; workers log connect errors | restart container/PG; verify chain; replay `dead_letter_jobs` |
| **Provider outage** | circuit breaker trips OPEN; `/health/dependencies` red for that provider | fail fast, no requests attempted; HALF_OPEN probe after `reset_seconds`; success re-closes |
| **Worker stale/heartbeat loss** | `WorkflowWorker.recover_stale()` reclaims jobs past threshold | job re-queued, not lost |
| **Job repeatedly fails** | retry-with-backoff exhausted | moved to **`dead_letter_jobs`** (never silently dropped); reconcile/manual replay |
| **App crash loop** | `/health/ready` 503, no `system_health_records` | restart with same env; audit chain verifies nothing was corrupted |
| **Encryption key lost/mismatch** | `SECRET_KEY_MISMATCH` denial on retrieve | restore key from secret manager; do NOT re-encrypt (key lineage rotates, never dumps) |

### Redis loss

Redis is not a source of truth (DB queue + cache). On loss: restart Redis,
repopulate caches from DB. The `WorkflowQueue` is DB-backed, so queued jobs
survive.

---

## 6. Immutable audit as a DR foundation

`audit_events` is append-only and SHA-256 hash-chained (`prev_hash`). Any
partial restore, manual edit, or dropped write **breaks the chain** and is
detected by `verify_chain()` — so a restored database is provably clean before
you trust it. `audit` and `security_events` are excluded from hard-delete
retention semantics; a DR restore never loses them.

---

## 7. DR checklist (put this in your runbook)

- [ ] WAL archiving on, full nightly dump, offsite copy
- [ ] `SECRET_ENCRYPTION_KEY` + `JWT_SECRET_KEY` backed up in the secrets vault
- [ ] Restore drill quarterly; `verify_chain` INTACT after each
- [ ] `/health/live|ready|dependencies` paged on red
- [ ] DLQ reviewed each incident or weekly
- [ ] Worker heap (heartbeat, stale recovery) enabled in prod
- [ ] Readiness gate green: `python -m app.checks.production_readiness`
