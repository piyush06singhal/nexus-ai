# NEXUS — Phase 11 Security & Governance Architecture

Reference for the security, governance, observability, and production-hardening
layer added in **Phase 11**. It is an *enforcement* layer on top of Phases 0–10 —
everything here **composes** existing systems; nothing is a second
execution/memory/company/verification/tool/approval/event system.

The invariants it enforces form a chain — each link gates the next:

```text
IDENTITY → AUTHORIZATION → POLICY → RESOURCE LIMIT → APPROVAL
        → ACTION → VERIFICATION → AUDIT → OBSERVABILITY → RECOVERY
```

If any link refuses, the operation stops and **the refusal is recorded**
(audit event + security event where applicable) — never silently dropped.

---

## 1. Threat model in one page

| Asset | Threat | Primary control |
|---|---|---|
| Sessions / tokens | Token theft, reuse, forgery | HS256-signed access tokens (15 min), hashed refresh, rotation/revocation |
| User accounts | Credential stuffing | PBKDF2, lockout + `AUTH_FAILURE` events |
| Company data | Cross-tenant access | Identity `company_id` + §7 authorization chain; cross-company ⇒ DENY + event |
| Secrets | Exfiltration at rest/in logs | Fernet AES-256-GCM at rest, env-key-only, redaction filter, mask hints |
| Outbound HTTP | SSRF / DNS rebinding | URL + host check per request and per redirect hop |
| Tool calls | Permission self-escalation | Static escalation guard in `ToolExecutor` (name + arg-key + regex) |
| Model input | Prompt injection | `PromptInjectionDetector` over untrusted observations → `PROMPT_INJECTION` events |
| Workloads | Runaway cost/iteration loops | `RunawayGuard` budget frames + `resource_limits` |
| Filesystem | Symlink escape, credential reads | Realpath containment + expanded deny list + special-file refusal |
| Providers | Outage cascades | Circuit breaker, dead-letter queue, health/readiness probes |
| Audit trail | Tampering | Append-only hash-chained `audit_events` + `verify_chain()` |

Full detail: [threat-model.md](threat-model.md).

---

## 2. Components

All in `apps/api/app/security/` (services) and `apps/api/app/security/api/`
(routers), plus enforcement in `app/core/` and Phase 10 modules that Phase 11
hardened (SSRF, filesystem, tool, context).

| Concern | Module | Exposed surface |
|---|---|---|
| Principal registry | `security/identity.py` — `IdentityManager`, `UserAccountManager` | `/security/access` (users, identities) |
| Authentication | `security/auth.py` + `tokens.py` + `sessions.py` | `/auth/login`, `/auth/logout`, `/auth/refresh`, `/auth/session` |
| RBAC/ABAC | `security/authorization.py` — `RoleService`, `AuthorizationService` | roles, permissions, sessions |
| Policy engine | `security/policy.py` — `PolicyEngine` (composes `company/policies.py::PolicyResolver`) | `/governance/policies` |
| Secrets | `security/secrets.py` + `security/crypto.py` | `/security/secrets` (refs + masked only) |
| DLP / data | `security/data_protection.py` — classification, transfer policy, retention | `/data/*` |
| Audit | `security/accountability.py` — `AuditService` | `/audit`, `verify_chain()` |
| Detection | `security/detection.py` — events, threat rules, alerts, incidents, incident actions | `/security/events`, `/security/alerts`, `/incidents` |
| Kill switch | `security/governance.py` — `KillSwitchService`, `GovernanceGuard` | `/governance/status` |
| Resources | `security/resources.py` — `ResourceGovernanceService`, `RunawayGuard` | `/governance/resources`, `/governance/limits` |
| Approvals | `security/approvals.py` + `startup/gates.py::ApprovalGateManager` | `/governance/approvals`, `/break-glass` |
| Flags | `security/flags.py` — `FeatureFlagService` | feature flags |
| Tool security | `security/tool_security.py` — sandbox + escalation guard | enforced in `ToolExecutor` |
| Context security | `security/context.py` — `PromptInjectionDetector` | enforced on untrusted observations |
| Observability | `core/telemetry.py`, `core/metrics.py`, `core/redaction.py`, `core/middleware.py` | `/system/metrics`, `/health/*` |
| Readiness | `checks/production_readiness.py` | `python -m app.checks.production_readiness` |

---

## 3. Identity → Authentication → Authorization

### 3.1 Identity (`identity` table)

One table unifies principals — `identity.kind` ∈ {`user`, `service`, `ai_employee`, `agent`, `company`},
with `status` ∈ {`active`, `suspended`, `revoked`, `disabled`} and `company_id`
scoping (or `company_scope_all` for platform scope). Human logins add a `user`
row (email, PBKDF2 password hash — no bcrypt dependency, standard library
HMAC-PBKDF2 via `cryptography`).

### 3.2 Sessions & tokens

- **Access token**: short-lived (15 min), HMAC-SHA256 (HS256) signed JSON via
  stdlib `hmac`/`base64` — no JWT dependency. Claims carry issuer, audience,
  subject identity, expiry, session id, `jti`. Unsigned or tampered tokens are
  rejected; algorithm is pinned to HS256.
- **Refresh token**: opaque, 256-bit random; only its **hash** is stored
  (`sessions.token_hash`, unique). Rotation issues a new refresh each use; a
  used refresh is `REPLACED`, an explicit logout `REVOKED`, expiry `EXPIRED`.
- **Enforcement**: the `AuthMiddleware` runs when `auth_enabled=true`
  (production). It whitelists only `/auth/login`, `/auth/logout`,
  `/auth/refresh`, docs, and health — **including `/auth/session`** (that route
  requires a valid token). Invalid/revoked/expired ⇒ `401 invalid_token`;
  repeated failures become `AUTH_FAILURE`/`TOKEN_INVALID` events and feed the
  login lockout.
- **Gate**: `auth_enabled` is `False` in dev/test so the Phase 0–10 suites run
  open, unchanged; production sets it true and `production_readiness` **FAILs**
  a production environment with it off.

### 3.3 Authorization chain (`AuthorizationService.authorize`)

```text
active identity?  →  company isolation?  →  role → permission  →  policy engine
   (status)                 (cross-company ⇒ DENY + event)    (most-restrictive; can
                                                            elevate to REQUIRE_APPROVAL)
```

- **Roles**: 8 system roles seeded (`platform_admin`, `company_admin`,
  `executive`, `operator`, `analyst`, `read_only`, plus service roles) onto
  `roles`/`permissions`/`role_permissions`/`user_role`. `platform_admin` holds
  a wildcard.
- **Policy engine** (`PolicyEngine.evaluate`): composes `PolicyResolver` so the
  hierarchy stays most-restrictive-wins; a policy match can downgrade a
  granted permission to DENY or REQUIRE_APPROVAL. Every decision that blocks is
  recorded to `policy_decisions` (auditable) and surfaced as a security event.
- **Every denial is a security event**: `PERMISSION_DENIED`,
  `POLICY_DENIED`, `CROSS_COMPANY_ACCESS`, `SECRET_ACCESS_DENIED`.

---

## 4. Policy, resource limits, approvals (governance)

### 4.1 Kill switch (`system_flags`)

Scopes: `GLOBAL / COMPANY / EMPLOYEE / AGENT / EXTERNAL / WORKFLOW`. Each is a
`*_PAUSED` flag (e.g. `external_paused`). `GovernanceGuard` is consulted at
the single choke points: `ExternalActionManager.create`, browser/computer
session creation, the workflow engine, the orchestrator, and the agent runtime.
A paused scope raises `GovernancePausedError` (a `PermissionDeniedError`), and
each pause/resume is audited (`governance.pause`/`governance.resume`).

### 4.2 Resource governance (`resource_limits`, `resource_usage`)

`ResourceGovernanceService` tracks categories (tokens, cost, executions, tool
calls, external actions, …) per period, with company overrides above hardened
defaults. `RunawayGuard` wraps agent/workflow workloads: a `RunawayGuardFrame`
records iterations/tool-calls/tokens/cost and raises `RunawayGuardStopped`
when any budget is exceeded. Excesses produce `RESOURCE_EXCEEDED` events.

### 4.3 Approvals & break-glass

- **Approval hardening** composes `ApprovalGateManager`:
  `approval_self_approval_blocked=true` and, by default, **separation of
  duties** (`requester ≠ approver`) are validated via `ApprovalGovernance`.
  High-risk external actions (`external_action_approval`) are one-gate-one-
  action-once.
- **Break-glass** (`break_glass_access`): explicit activation, mandatory
  reason, time limit (`break_glass_default_max_minutes=30`), optional elevation
  for an incident window, **auto-expiry**, and full audit.

---

## 5. Secrets, encryption, data governance

- **Encryption** (`security/crypto.py`): Fernet (AES-256-GCM) via
  `cryptography>=43`; key material comes **only** from env
  (`SECRET_ENCRYPTION_KEY`). Test/dev may auto-derive an ephemeral key;
  production **must** provide one or the readiness check FAILs.
- **Secrets** (`secrets` + `secret_versions` + `encryption_keys`): ciphertext
  at rest, `key_id` for graceful multi-key rotation, `mask_hint` only (no
  plaintext in serialization/logs/apartial outputs — asserted), rotation-due
  schedule, revoke ⇒ read returns `PermissionDeniedError`. Composes the Phase 10
  `CredentialVault` reference-only credentials.
- **DLP & classification** (`security/data_protection.py`): explicit
  `data_classifications` (public → secret); `DataTransferPolicy.evaluate`
  chains declared class → payload re-classification → outbound floor
  (`max_outbound=confidential`), composing the Phase 10
  `external/security/exfiltration.py` guard. Blocked transfers and
  restricted-data passes are `DATA_EXFILTRATION_BLOCKED` events.
- **Retention** (`retention_policies`): entity types (executions, logs, audit,
  security events, memory, observations, tool calls, screenshots) with
  semantics `hard / soft / anonymize / retention-lock`. **Audit and security
  events are never casually hard-deleted** (`_RETAINED_ENTITY_TYPES`); their
  default retention is "keep forever". `--reset` demos never purge them.

---

## 6. Observability & reliability

- **Telemetry**: `contextvars` request/trace ids propagate into JSON logs,
  error envelopes, and metrics labels.
- **Redaction**: a single redaction filter (`core/redaction.py`) scrubs
  PII/secret patterns from *all* structured logs and responses — a defense even
  a developer forgets to invoke.
- **Metrics** (`core/metrics.py`): dependency-free registry — request/error/
  latency, agent, tool, external, verification, recovery, queue, provider,
  model-token counters.
- **Middleware chain** (`core/middleware.py`): request-id → security headers →
  trusted hosts → request-size cap → rate limits (default/auth/external/
  expensive buckets) → idempotency (`Idempotency-Key` header).
- **Health**: `/health/live`, `/health/ready`, `/health/dependencies`
  (never leaks secrets) → `system_health_records`.
- **Reliability**: worker heartbeat + stale recovery, retry-with-backoff, and a
  **dead-letter queue** (`dead_letter_jobs`) so failed jobs are never silently
  lost.

---

## 7. Hardened Phase 10 surfaces

- **SSRF** (`external/api/ssrf.py` + `http_client.py`): scheme/host/userinfo
  checks, blocked private/link-local/metadata ranges, **DNS-rebinding test**
  (`check_host_resolution`), and **re-validation of every redirect hop**.
- **Filesystem** (`external/files/security.py`): `.resolve()` containment,
  symlink pre-flight, expanded system/credential deny list, special-file
  refusal.
- **Tool security** (`security/tool_security.py`): per-tool `ToolSandbox`
  (timeout/memory/cpu/output budget; fs/network/process toggles) with template
  heuristics, and a **static self-escalation guard** — a tool cannot grant
  permissions, change roles/policy, or bypass approvals, detected by name
  catalog, recursive arg-key walk, and regex patterns.
- **Context security** (`security/context.py`): trusted/untrusted source
  authorities; `PromptInjectionDetector` layered detection over untrusted
  observations → `PROMPT_INJECTION` events.

---

## 8. Data model (Phase 11 additions, migration `0013_security_governance`)

```text
identity  user  session  role  permission  role_permission  user_role
policy_rule  policy_decision
secrets  secret_version  encryption_key
audit_events (hash chain)  security_events  security_alerts  incidents
system_flags  resource_limits  resource_usage  rate_limit_records  feature_flags
dead_letter_jobs  idempotency_keys  system_health_records
data_classifications  retention_policies  governance_controls  break_glass_access
context_authorities
```

The migration is **additive** (no destructive change to Phase 0–10 tables).
All new tables follow the repo conventions: StrEnum stores VARCHAR
(`native_enum=False`), UUID PK `default=uuid4`, `company_id` FK + index where
tenant-scoped, `created_at` server-default.

---

## 9. API map (Phase 11 routers)

Mounted under `/api/v1` (all under `app/security/api/`). Enforced globally only
when `auth_enabled`; `/auth/login|logout|refresh`, docs, and health stay
whitelisted.

- `/auth` — `POST /login`, `POST /logout`, `POST /refresh`, `GET /session`
- `/access` — users (`GET/POST`, `POST /users/{id}/roles`), roles, permissions,
  secrets **refs only** (`GET/POST /secrets`, `DELETE /secrets/{id}`)
- `/security` — `GET /events`, `GET /alerts`, `POST /alerts/{id}/acknowledge|resolve`,
  `GET/POST /incidents`, `GET /audit`, `GET /audit/verify`
- `/governance` — `GET /flags`, `POST /flags/{scope}/pause|resume`,
  `GET/POST /policies`, `GET /policy-decisions`, `GET/POST /limits`,
  `GET /resources/usage`, `GET /controls`, `GET/POST /break-glass`
- `/data` — `GET /classifications`, `POST /transfer-check`, `GET/POST /retention`
- `/system` — `GET /health/live|ready|dependencies|overview`, `GET /metrics`,
  `GET/POST /feature-flags`, `GET /health-records`

---

## 10. Deployment items (documented, not claimed)

These are **honest WARN** items in `production_readiness` and are intentionally
*not* claimed as implemented:

- **OS-level process sandboxing** for tool execution (in-process speculative
  sandboxes are enforced; OS namespace/cgroup isolation is a deployment item).
- **Redis-backed job workers** (a DB-backed `WorkflowQueue` + daemon worker is
  active; a Redis worker pool is a deployment item).
- **Managed secrets vault** externalization (Fernet with env keys is in-process;
  KMS/vault integration is a deployment item).
- **TLS termination** (`tls_enabled` flag; normally terminated upstream).
- No compliance certifications (§88) are claimed.
