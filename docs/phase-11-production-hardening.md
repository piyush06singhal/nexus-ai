# NEXUS — Phase 11 Production Hardening (What Changed)

What Phase 11 actually delivered, how to run it, and how to verify it. Companion
to [security-architecture.md](security-architecture.md) (design) and
[threat-model.md](threat-model.md) (threat lens).

---

## 1. High-level

Phase 11 turned NEXUS from "powerful autonomous AI company platform" into a
**secure, governed, observable, resilient, production-oriented** one. It is an
*enforcement layer* that composes Phases 0–10 — no second execution/memory/
company/verification/tool/approval/event system was added. Adding authentication
where none existed is the spine: **ID → AUTHZ → POLICY → RESOURCE LIMIT →
APPROVAL → ACTION → VERIF → AUDIT → OBSERVABILITY → RECOVERY**, and every
refusal is *recorded*, never silently dropped.

### Design decisions locked

1. **`cryptography>=43`** for real encryption at rest (Fernet = AES-256-GCM).
   Keys come **only** from env (`SECRET_ENCRYPTION_KEY`, `JWT_SECRET_KEY`).
   `production_readiness` FAILs production without them.
2. **Auth is gated** — `auth_enabled=true` only in production. Dev/test keep
   running open so the ~950 pre-existing tests stay green; the Phase 11 suite
   flips auth on per-test and proves the enforcement.
3. **No JWT dependency** — signed tokens are HS256 HMAC via stdlib
   (issuer/audience/expiry pinned; unsigned/tampered rejected).
4. **Append-only audit** — hash-chained `audit_events` with a `verify_chain()`
   endpoint; audit and security events are never casually hard-deleted.

---

## 2. What landed, wave by wave

**Wave A — Foundation.** `cryptography` dep; ~60 settings + `.env.example`;
30 new tables (`app/db/models/security.py`); additive migration
`alembic/versions/0013_security_governance.py`.

**Wave B — Identity & Auth.** `identity` unifying user/service/employee/agent/
company principals; `user` logins with PBKDF2; session lifecycle
(`session` → created/refreshed/revoked/expired, refresh stored hashed, rotation,
lockout); HS256 tokens; RBAC/ABAC — `RoleService` seeds 8 system roles,
`AuthorizationService` runs the §7 chain, `PolicyEngine` composes the Phase 2
`PolicyResolver` (most-restrictive-wins).

**Wave C — Secrets & DLP.** `SecretManager`/`KeyManager` (Fernet at rest,
multi-key rotation, refs + mask hints only — no plaintext in logs/DB/API);
`DataClassificationService` + `DataTransferPolicy` composing the Phase 10
exfiltration guard; `RetentionService` (see [data-governance.md](data-governance.md)).

**Wave D — Audit, detection, incidents, kill switch.** `AuditService` (append-only,
hash chain, `verify_chain()`); 13-category `SecurityEventService`;
`ThreatDetectionService` rules; `SecurityAlertService` (mirrors Phase 8
`AlertManager`); `IncidentService` + `IncidentActionExecutor` (§85 audited
containment actions); `KillSwitchService`/`GovernanceGuard` over
`system_flags` scopes (GLOBAL/COMPANY/EMPLOYEE/AGENT/EXTERNAL/WORKFLOW).

**Wave E — Governance.** `FeatureFlagService` (env → global → company);
`ResourceGovernanceService` + `RunawayGuard` budget frames; approval hardening
(self-approval blocked, separation of duties, expiration, resource/data/budget
impact recorded); `BreakGlassService` (reason, time limit, auto-expiry, audit;
no stealth elevation).

**Wave F — Reliability & observability.** `core/telemetry.py`
(request/trace ids), `core/metrics.py` (dependency-free registry),
`core/redaction.py` (central PII/secret filter), JSON structured logging;
middleware chain — request-id, security headers, trusted hosts, request-size,
rate limits, idempotency; worker heartbeat/stale recovery + `dead_letter_jobs`
DLQ; `/system/health/live|ready|dependencies|overview` + `system_health_records`;
`/system/metrics`.

**Wave G — Hardening composes Phase 10.**
- **SSRF** — redirect-hop revalidation + DNS-rebinding resolution check, per
  request; link-local/metadata/private ranges blocked (`app/external/api/ssrf.py`,
  enforced in `SecureHTTPClient`).
- **Filesystem** — `.resolve()` containment, symlink pre-flight, expanded
  system/credential deny list (`.env`, SSH keys, cloud creds, keyrings, config
  files), special-file refusal (`app/external/files/security.py`).
- **Tools** — `ToolSandbox` per-tool budget + allowed contexts and a **static
  self-escalation guard** wired into `ToolExecutor` (a tool cannot grant
  permissions, change roles/policy, or bypass approvals; blocked calls become
  `DENIED` tool records + events).
- **Context** — trusted/untrusted authority model; `PromptInjectionDetector`
  over untrusted observations (`IGNORE PREVIOUS…`, `REVEAL SECRET…`, `CHANGE
  POLICY…`, `DISABLE SECURITY…`, `SEND DATA ELSEWHERE…`) → `PROMPT_INJECTION`
  events.
- **Kill switch enforcement** — `GovernanceGuard` added to
  `ExternalActionManager.create`, `BrowserSessionManager.create`,
  `ComputerSessionManager.create` (`SystemFlagScope.EXTERNAL`).
- **Retention** — `RetentionService.set_policy/purge_due/purge_execute`
  (hard/soft/anonymize/retention-lock; audit/security never hard-deleted).

**Wave H — API.** Routers under `/api/v1` (map in
[security-architecture.md](security-architecture.md) §9): `/auth`, `/access`,
`/security` (`events`, `alerts`, `incidents`, `audit`), `/governance`
(`flags`, `policies`, `limits`, `resources`, `break-glass`), `/data`
(`classifications`, `transfer-check`, `retention`), `/system`
(health/, metrics, feature-flags). Schemas in `app/schemas/security.py`.
Secrets serialize as **refs + mask only**.

**Wave J — Checks & demos.** `python -m app.checks.production_readiness`
(PASS/WARN/FAIL; FAILs a production env without auth/encryption keys) and
`python -m scripts.seed_security_governance [--reset]` (7 attacks blocked,
failure-recovery demo, 100-task benchmark, audit-chain verification).

---

## 3. Configuration (`.env` / settings)

Key Phase 11 settings (see `app/core/config.py` — `Settings`):

```bash
# Gate authentication (TRUE in production)
AUTH_ENABLED=true
JWT_SECRET_KEY=<random hex>            # HMAC-SHA256 signing key
SECRET_ENCRYPTION_KEY=<fernet key>     # AES-256-GCM at-rest key
SECURE_AUTH_COOKIES=false              # set true behind TLS
TRUSTED_HOSTS=["api.example.com"]      # Host-header allow-list
LOGGING_JSON=true                      # structured logs
TLS_ENABLED=false                      # upstream termination flag

# Rate limiting (sliding window)
RATE_LIMIT_ENABLED=false
RATE_LIMIT_DEFAULT_PER_MINUTE=600
RATE_LIMIT_AUTH_PER_MINUTE=20

# Feature gates — risky capabilities default OFF
FEATURE_SELF_SERVE_SIGNUP_ENABLED=false
FEATURE_BROWSER_CLOUD_EXPORT_ENABLED=false
FEATURE_EXTERNAL_AUTONOMOUS_SEND_ENABLED=false
FEATURE_DATA_EXPORT_ENABLED=false
FEATURE_CODE_EXECUTION_ENABLED=false

# Governance / approvals
APPROVAL_SELF_APPROVAL_BLOCKED=true
APPROVAL_REQUIRE_SEPARATION_OF_DUTIES=true
BREAK_GLASS_DEFAULT_MAX_MINUTES=30
ADMIN_ACTION_REQUIRE_APPROVAL=false

# Reliability
WORKFLOW_WORKER_ENABLED=false    # run the worker process in prod
DLQ_ENABLED=true
IDEMPOTENCY_ENABLED=true

# Retention (days; 0 = keep forever)
RETENTION_EXECUTION_DAYS=180
RETENTION_LOGS_DAYS=180
RETENTION_SECURITY_EVENTS_DAYS=0
RETENTION_MEMORY_DAYS=730
```

Dev/test: leave `AUTH_ENABLED` unset (open); test environments auto-derive
ephemeral signing/encryption keys.

---

## 4. Running the verifications

From `apps/api` (venv `apps/api/.venv`):

```bash
# Unit verification (+ the demo + readiness)
.venv/bin/python -m pytest tests/test_security_phase11.py tests/test_external_security.py -q
.venv/bin/python -m pytest tests/test_tool_executor.py tests/test_tool_api.py -q

# Demo (SQLite or Postgres; --reset to rebuild demo data) — asserts every attack
DATABASE_URL="sqlite:////tmp/nexus_secdemo.db" \
  .venv/bin/python -m scripts.seed_security_governance [--reset]

# Production readiness (0 = ready, 1 = blocking FAIL)
ENVIRONMENT=production AUTH_ENABLED=true JWT_SECRET_KEY=… SECRET_ENCRYPTION_KEY=… \
  .venv/bin/python -m app.checks.production_readiness

# Full regression + lint/format
.venv/bin/pytest -q
.venv/bin/ruff check app tests scripts && .venv/bin/ruff format --check app tests scripts
```

---

## 5. Known honest limits (documented, not claimed)

- **OS-level process sandboxing** for tool execution is a *deployment item* —
  in-process `ToolSandbox` budgets are enforced, namespaces/cgroups are not.
- **Redis-backed workers** are a deployment item — the DB-backed
  `WorkflowQueue` + daemon `WorkflowWorker` (heartbeat, stale recovery, DLQ)
  is active today.
- **Managed secrets vault** (KMS/HashiCorp) is a deployment item — Fernet with
  env keys is in-process.
- **TLS termination** flagged, normally upstream.
- **`purge_execute`** sweeps `agent_executions`/`tool_calls`/`memories`
  **time-scoped only** (those tables have no `company_id` column); `company_id`
  is used for the policy lookup and audit provenance. Per-company physical
  storage isolation is a deployment item.
- The one pre-existing full-suite ordering flake
  (`test_full_orchestrator_pipeline`) passes in isolation and is not a Phase 11
  regression.
- No compliance certifications are claimed (§88).
