# NEXUS — Security Reference

**Scope**: This document consolidates the Phase 11 security, governance, and
production-hardening layer with cross-links to the threat model and related
docs. It is **not** a formal compliance certification (SOC2, HIPAA, FedRAMP,
etc.); no such claims are made. All controls are implemented as layered
application-level policy inside the process boundary — OS-level isolation,
managed vaults, and hardware security modules are deployment concerns, not
claims.

---

## 1. Threat Model Overview

See `threat-model.md` for the full asset → threat → control → verification map.
The invariant chain is:

```
IDENTITY → AUTHORIZATION → POLICY → RESOURCE LIMIT → APPROVAL → ACTION
→ VERIFICATION → AUDIT → OBSERVABILITY → RECOVERY
```

Key threat categories covered:

| Threat | Controls | Verification |
|--------|----------|--------------|
| Token theft/forge (T1) | HS256-only, 15 min access, hashed refresh, rotation, lockout | `test_login_refresh_logout_session_flow`, `test_*_rejected` |
| Cross-tenant access (T2) | `company_id` FK + index on every table, `AuthorizationService` short-circuit | `test_cross_company_access_denied_and_event_recorded` |
| Secret exfiltration (T3) | Fernet AES-256-GCM at rest, redaction filter, mask hints, TLS-terminated | `test_secret_encryption_round_trip`, `test_redaction_filter` |
| Prompt injection (T4) | `PROMPT_INJECTION_PROTECTION_ENABLED`, classifier middleware, tool sandbox | `test_prompt_injection_blocked` |
| SSRF (T5) | `SSRF_PROTECTION_ENABLED`, allowlist CIDR, deny private ranges, DNS pinning | `test_ssrf_blocked_private_ranges` |
| Tool/action abuse (T6) | Capability registry, risk→policy→approval, execution journal, permission gating | `test_tool_action_permission_denied` |
| Marketplace abuse (T7) | Metadata-only, `PackageScanner`, approval-gated install, evidence-based recs | `test_marketplace_package_scanner`, `test_install_approval_required` |
| Simulation isolation (T8) | Sandboxed engine, SIMULATED/FORECAST labels, no real side effects, resource ceilings | `test_simulation_sandboxed_no_mutation` |
| Audit integrity (T9) | Append-only hash-chained log, `/audit/verify` endpoint | `test_audit_chain_verification` |

---

## 2. Authentication & Authorization

**Auth stack** (`app/security/auth/` + `app/security/api/middleware.py`):

- **Bearer tokens** (HS256, `JWT_SECRET_KEY` from env): access 15 min, refresh 7 days
- **Middleware**: `AuthMiddleware` enforces on `/api/v1/*` except whitelisted paths
  - Whitelist: `/api/v1/health/*`, `/api/v1/health`, `/api/v1/auth/login`, `/api/v1/auth/register`, `/docs`, `/openapi.json`, `/redoc`
- **RBAC/ABAC**: `AuthorizationService.authorize(principal, action, company_id)`
  - Role grants are company-scoped; no cross-company permission bleed
  - `company_scope_all` super-admin flag exists but is gated
- **Policy engine**: `PolicyEngine` (Phase 11) composes per-company policies; most-restrictive-wins
- **Dev bootstrap**: `AUTH_DEV_BOOTSTRAP_EMAIL/PASSWORD` create admin on first startup when `AUTH_ENABLED=false` and no admin exists — **never enable in production**

**Production gates** (`app/checks/production_readiness.py` FAILs if):
- `AUTH_ENABLED=false`
- `JWT_SECRET_KEY` empty
- `SECRET_ENCRYPTION_KEY` empty
- `SECURE_AUTH_COOKIES=false` (should be true behind TLS)

---

## 3. Tenant Isolation

- Every company-scoped table has `company_id UUID NOT NULL REFERENCES company(id)` + index
- `_company_or_404` convention (Phase 8) keeps non-members blind (404, not 403)
- `Identity.company_id` bound at token issuance; cross-company intent = DENY + `CROSS_COMPANY_ACCESS` security event
- Database-level: no row-level security (PostgreSQL RLS not used); isolation is enforced in `AuthorizationService` and service-layer queries

---

## 4. Secret Management

- **At rest**: Fernet AES-256-GCM (`cryptography.fernet.Fernet`) with `SECRET_ENCRYPTION_KEY` from env only — never committed
- **Ciphertext** stored in `secrets` / `secret_version` tables; plaintext never in DB
- **In transit**: TLS terminated upstream; `SECURE_AUTH_COOKIES=true` in production
- **In logs/memory**: Central redaction filter (`app/core/redaction.py` + `logging.py`) masks tokens, API keys, secrets, PII via regex + contextual patterns
- **Mask hints**: secret metadata stores `hint` (first 4/last 4 chars, type) — never reversible to value

---

## 5. Prompt Injection Defense

- `PROMPT_INJECTION_PROTECTION_ENABLED=true` (default) activates classifier middleware
- User-supplied text (agent prompts, tool arguments, external observations) scanned before reaching provider
- Structured-output schema validation (pydantic) on model responses
- Tool sandbox: each tool executes in a constrained context; no shell access; file operations path-contained

---

## 6. SSRF Protection

- `SSRF_PROTECTION_ENABLED=true` (default) enforces:
  - Deny private CIDR ranges (RFC 1918, loopback, link-local, metadata endpoints)
  - Allowlist `EXTERNAL_ALLOWED_CIDRS` for known-safe ranges
  - DNS pinning (first resolve → validate IP → connect)
  - Timeout/budget caps: `EXTERNAL_CONNECT_TIMEOUT_SECONDS`, `EXTERNAL_READ_TIMEOUT_SECONDS`, `MAX_EXTERNAL_PAYLOAD_BYTES`
- Generic HTTP connector is **OFF by default** (`EXTERNAL_GENERIC_HTTP_CONNECTOR_ENABLED=false`)

---

## 7. Tool & Action Security

- **Capability registry**: every external capability registers as a Phase 2 tool with risk tier (LOW/MEDIUM/HIGH/CRITICAL)
- **Governance funnel**: `risk → policy → approval → execution → verification → recovery → audit`
- **Reference-only credentials**: connection secrets NEVER stored in DB; resolved at use-time from `INTEGRATION_<PROVIDER>_SECRET` / `INTEGRATION_<PROVIDER>_API_KEY` env vars (dev convenience; managed vault is a deployment item)
- **Data classification ceiling**: `EXTERNAL_OUTBOUND_CLASS` (public|internal|confidential|restricted|secret)
- **Action journal**: immutable `external_action_journal` table with hash-chained audit entries

---

## 8. Marketplace Security

- **Metadata-only**: no executable code stored; packages are capability/skill descriptions
- **Static analysis**: `PackageScanner` validates manifest (capabilities, skills, task types, permissions, dependencies, security class)
- **Approval-gated install**: `require_approval=True` → `ApprovalGateManager` gate (Phase 9); `confidential` class always requires approval
- **Evidence-based recommendations**: `RecommendationEngine` scores by attached benchmark results, not vendor claims
- **No auto-execute**: installation records intent only; runtime execution goes through normal governance

---

## 9. Simulation Isolation

- `SimulationEngine` runs in a **sandboxed** mode (`sandboxed=True` on every `Simulation`)
- All outputs explicitly labeled `SIMULATED` or `FORECAST` — **never `ACTUAL`**
- Digital-twin snapshots are read-only; no writes to production tables
- Engine hard ceilings (constructor defaults): `max_ticks=500`, `max_events=5000`, `max_iterations=50`, `run_timeout_seconds=60`
- Per-day resource budgets via Phase 11 governance (`sim_runs`, `sim_iterations`, `sim_events`)
- Concurrency ceiling: `MAX_CONCURRENT_PHASE12_RUNS = 8` (constant in `app/phase12/governance.py`)

---

## 10. Audit Logging

- Append-only `audit_events` table with `prev_hash` forming a hash chain
- Endpoint: `GET /api/v1/security/audit?company_id=...&limit=...`
- Verification: `GET /api/v1/security/audit/verify?company_id=...` — recomputes chain, reports tamper index or OK
- Security events (`security_events`) cover: auth failures, cross-company access, prompt injection, SSRF, tool violations, kill-switch triggers, resource limit breaches, approval escalations

---

## 11. Incident Response

- Detection (13 categories) → `Alert` → `Incident` → Containment → Resolution
- Containment actions: `pause`, `quarantine`, `revoke_tokens`, `kill_switch`
- `incident_response.md` has the full playbook and API endpoints (`/api/v1/security/incidents`, `/alerts`, `/containments`)

---

## 12. Kill Switch & Resource Limits

- **Global kill switch**: `KILL_SWITCH_GLOBAL_PAUSE=true` pauses autonomy across all tenants instantly
- **Per-scope kill switch**: `SystemFlagScope` (EXTERNAL, SIMULATION, OPTIMIZATION, etc.) via `/api/v1/governance/flags`
- **Resource limits**: `/api/v1/governance/limits` — categories: `iterations`, `duration_seconds`, `tokens`, `cost`, `tool_calls` (Phase 11); Phase 12 adds `sim_runs`, `sim_iterations`, `sim_events`, `optimization_candidates`, `benchmark_runs`, `benchmark_cases`, `experiment_runs`, `marketplace_ops`
- **Enforcement**: checked before every orchestration/simulation/optimization run; hard ceilings in engine constructors

---

## 13. Observability & Reliability

- **Telemetry**: request/trace IDs via `ContextVar` (`app/core/telemetry.py`)
- **Metrics**: `app/core/metrics.py` registry (counters, gauges, histograms)
- **Redaction**: central filter masks tokens/secrets/PII in logs
- **Middleware**: auth, rate limiting, security headers, trusted hosts, request body caps
- **Workers/queues**: DB-backed queue (`workflow_queue`), `DLQ_ENABLED`, `IDEMPOTENCY_ENABLED`, `WORKER_HEARTBEAT_INTERVAL_SECONDS=5`, `WORKER_STALE_THRESHOLD_SECONDS=120`
- **Health probes**: unauthenticated `/api/v1/health/{live,ready,dependencies}` (Docker healthcheck-ready); auth-bound equivalents at `/api/v1/system/health/*`

---

## 14. References

| Doc | Scope |
|-----|-------|
| `threat-model.md` | Assets, threats, controls, verification tests |
| `security-architecture.md` | AuthZ architecture, policy engine, secret management |
| `data-governance.md` | Tenant isolation, retention, classification |
| `incident-response.md` | Detection→alert→incident→containment→resolution playbook |
| `phase-11-production-hardening.md` | Full implementation notes, production gates, config inventory |

---

## 15. What This Is Not

- **No compliance certifications** — this is implementation documentation, not an audit report
- **No production SLAs** — dev-environment measurements only
- **No managed vault** — `SECRET_ENCRYPTION_KEY` / `JWT_SECRET_KEY` from env; external integration secrets from env; a vault integration is a deployment concern
- **No network isolation** — OS/container-level isolation is a deployment concern