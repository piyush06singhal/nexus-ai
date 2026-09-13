# NEXUS — Threat Model

A concise threat model for the NEXUS platform, mapping **assets → threats →
Phase 11 controls → verification**. Worked through the invariant chain
`IDENTITY → AUTHORIZATION → POLICY → RESOURCE LIMIT → APPROVAL → ACTION →
VERIFICATION → AUDIT → OBSERVABILITY → RECOVERY` — each control below sits on
that chain.

Scope honesty: the simulated/fixture nature of the current infrastructure means
several controls are *layered policy* enforced inside the process; OS-level
isolation and managed secrets infrastructure are documented deployment items,
not claimed here.

---

## 1. Assets

| # | Asset | Kind | Where it lives |
|---|---|---|---|
| A1 | User / identity accounts | Confidentiality, integrity | `identity`, `user`, `session` |
| A2 | Credentials & secrets | Confidentiality | `secrets`, `secret_version`, `encryption_key`, env | 
| A3 | Company/tenant data | Confidentiality, integrity, isolation | all company-scoped tables |
| A4 | Agent/tool actions & executions | Integrity, audit | `agent_executions`, `tool_calls`, tool registry |
| A5 | Outbound network calls | Availability, confidentiality | `SecureHTTPClient`, integrations |
| A6 | Browser/computer sessions | Integrity, safety | `browser_*`, `computer_*` |
| A7 | Audit & security events | Integrity (non-repudiation) | `audit_events`, `security_events` |
| A8 | Worker/queue jobs | Availability | `workflow_queue`, `dead_letter_jobs` |
| A9 | Model prompts & observations | Confidentiality, integrity | runtime context, `memory` |

---

## 2. Threat list (STRIDE-flavored)

### T1 — Token theft / reuse / forgery  *(A1, Spoofing)*
**Attack:** steal an access token from a log; replay a refresh token; forge a
token without the key; downgrade the algorithm.
**Controls:**
- Short-lived access tokens (15 min); opaque refresh stored **hashed** only.
- HS256-only, algorithm pinned; unsigned/tampered/expired rejected.
- Refresh rotation ⇒ reuse of a rotated token is a `TOKEN_INVALID` signal; revoke
  on logout.
- Login lockout after `max_failed_login_attempts`; `AUTH_FAILURE` events.
**Verification:** `test_login_refresh_logout_session_flow`,
`test_access_token_expiry`, `test_unsigned_or_tampered_token_rejected`,
`test_login_lockout`.

### T2 — Cross-tenant access  *(A3, Information disclosure)*
**Attack:** a principal in company A reads/writes company B resources by guessing
`company_id`; a service role reaches another tenant.
**Controls:**
- `Identity.company_id` + `company_scope_all`; `AuthorizationService`
  short-circuits cross-company intent ⇒ DENY + `CROSS_COMPANY_ACCESS` event.
- Roles are resolved per company; a permission without a company grant does not
  apply across the boundary.
- Existing Phase 8 `_company_or_404` convention keeps non-members blind (404).
**Verification:** `test_cross_company_access_denied_and_event_recorded`.

### T3 — Secret exfiltration: at rest, in logs, in transit  *(A2, Information disclosure)*
**Attack:** read ciphertext `secrets`; watch logs/API for plaintext; scrape a
mask hint back to a value.
**Controls:**
- Fernet AES-256-GCM at rest; key from env only; multi-key rotation with
  `key_id` lineage.
- Serialization is refs + `mask_hint` only; `core/redaction.py` filter scrubs
  secret/PII patterns from every log line and response.
- DLP floor: `max_outbound=confidential`; restricted/secret never leaves
  without approval/allow-list. `DATA_EXFILTRATION_BLOCKED` events.
- Revoked secrets read ⇒ `PermissionDeniedError` + `SECRET_ACCESS_DENIED`.
**Verification:** `test_secret_store_retrieve_rotate_revoke`,
`test_redaction_filter_hides_credentials`, `test_no_plaintext_in_serialization`.

### T4 — SSRF / DNS rebinding  *(A5, Information disclosure)*
**Attack:** make the server fetch an internal address; a legitimate external
host resolves to a private IP (rebinding).
**Controls:**
- `check_url` (scheme/host/userinfo) + private/link-local/metadata/IPv6 blocklist.
- `check_host_resolution` re-checks **every host** (resolves through DNS; a
  private result blocks) and **every redirect hop** is re-validated.
- Circuit breaker + timeouts bound the blast radius.
**Verification:** `TestSecureHTTPSSRFIntegration::test_http_client_revalidates_redirect_hops`,
`test_ssrf_blocks_internal_targets`.

### T5 — Permission self-escalation via tools  *(A4, Tampering/Elevation)*
**Attack:** an agent calls a tool that grants itself admin, changes its role,
or bypasses an approval; a nested argument smuggles `allowed_tools: ["all"]`.
**Controls:**
- `ToolSecurityPolicy` static guard in `ToolExecutor` (step "3.5"):
  name catalog + recursive arg-key walk + regex patterns; nested dicts/lists
  are walked, `set_admin`, `grant_permission`, `allowed_tools`, `bypass` etc.
  are refused.
- Denied calls persist as `DENIED` tool records with `ToolSecurityError` and a
  warning log, plus deny-tools + per-tool `ToolSandbox` budgets.
**Verification:** `test_self_escalation_by_name_blocked`,
`test_self_escalation_by_argument_blocked`, `test_executor_refuses_escalation_via_registered_tool`.

### T6 — Prompt injection from untrusted content  *(A6/A9, Tampering)*
**Attack:** a web page / feedback / external observation contains
`ignore previous instructions`, `reveal secrets`, `disable security`,
`send data elsewhere`.
**Controls:**
- Observations tagged `EXTERNAL_UNTRUSTED_CONTENT`; `PromptInjectionDetector`
  layered rules (input classification + context isolation + tool policy +
  permissions + verification) → verdict `quarantine`/`review`, `PROMPT_INJECTION`
  events.
- Trusted/untrusted **source authority** model weights a verified internal
  source softer, but never skips the scan.
**Verification:** `test_prompt_injection_detected`, Phase 10 malicious-injection
fixture tests.

### T7 — Runaway workloads / cost loops  *(A4, Availability)*
**Attack:** an agent loops tool calls or tokens past budget; a workflow burns
duration; cost spirals.
**Controls:**
- `RunawayGuard` frames (iterations/duration/tool-calls/tokens/cost) raised by
  the runtime and workflows; `ResourceGovernanceService` per-company limits +
  `RESOURCE_EXCEEDED` events.
**Verification:** `test_runaway_guard_stops_over_budget_workload`,
seed demo attack 6.

### T8 — Filesystem escape / credential file reads  *(A1/A2, Disclosure)*
**Attack:** a tool resolves `../../etc/passwd`, a symlink back to the root, a
`.env`, `~/.ssh/id_rsa`, cloud credential or keyring file.
**Controls:**
- `.resolve()` containment + per-component symlink pre-flight; deny list of
  system + credential paths (`.env`, SSH/cloud creds, `.git-credentials`,
  keyrings, config); special-file refusal (FIFO/device).
**Verification:** `test_symlink_preflight_refused_inside_root`,
`test_expanded_deny_list_catches_home_and_cloud_creds`,
`test_refuses_symlink_to_special_file`.

### T9 — Abuse of kill switch / break-glass  *(Integrity)*
**Attack:** pause another tenant, or elevate with no reason/trace.
**Controls:**
- Kill-switch flags are scope+tenant specific, reason + set_by mandatory, every
  pause/resume audited; global pause is a deliberate platform operation.
- Break-glass needs explicit reason, time-limited (`break_glass_default_max_minutes`),
  auto-expiry, audited; no stealth elevation.
**Verification:** `test_kill_switch_pause_resume_guard`, `test_break_glass_activation_and_auto_expiry`.

### T10 — Audit tampering  *(A7, Repudiation)*
**Attack:** delete or silently rewrite audit rows to hide an action.
**Controls:**
- Append-only service layer (no UPDATE/DELETE API), SHA-256 **hash chain**
  (`prev_hash`) so any mutation breaks `verify_chain()`; audit + security events
  are excluded from hard-delete retention semantics.
**Verification:** `test_audit_chain_integrity`, `test_verify_chain_detects_tamper`,
`test_retention_never_hard_deletes_audit`.

### T11 — Provider outage / silent job loss  *(A8, Availability)*
**Attack:** an external provider goes down; a worker dies mid-job; a job fails
forever.
**Controls:**
- Circuit breaker (trips OPEN, fast-fail, HALF_OPEN reset), retry/backoff,
  **dead-letter queue** (failed jobs land in `dead_letter_jobs`, never silently
  lost), worker heartbeat + stale-job recovery, `/health/live|ready|dependencies`.
**Verification:** `test_circuit_breaker_trips_and_recovers`,
`test_worker_stale_recovery`, `test_dlq_receives_failed_jobs`.

### T12 — Rate abuse / oversized requests  *(Availability)*
**Attack:** brute-force the login; flood expensive endpoints; giant body.
**Controls:**
- Rate-limit buckets (default/auth/external/expensive), request-size cap,
  `RATE_LIMIT_EXCEEDED` events.
**Verification:** `test_rate_limit_exceeded`, `test_request_size_cap`.

---

## 3. Control-to-test index

| Control | Module | Tests |
|---|---|---|
| Token/session security | `security/auth.py`, `tokens.py` | `test_login_refresh_logout_session_flow`, token/expiry/lockout tests |
| Authorization chain | `security/authorization.py` | `test_company_admin_permissions`, `test_unknown_action_denied`, cross-company |
| Policy engine | `security/policy.py` | policy veto / most-restrictive-wins tests |
| Secrets + redaction | `security/secrets.py`, `core/redaction.py` | store/rotate/revoke, redaction, no-plaintext |
| SSRF | `external/api/ssrf.py`, `http_client.py` | `test_ssrf_*`, redirect-hop integration |
| Filesystem | `external/files/security.py` | `TestFilesystemHardening` (3) |
| Tool security | `security/tool_security.py`, `tools/executor.py` | `TestToolSecurity` (7) |
| Context security | `security/context.py` | prompt-injection tests |
| Kill switch / resources / approvals | `security/governance().resources().approvals()` | flag/guard, runaway, SoD/self-approval, break-glass |
| Audit | `security/accountability.py` | chain integrity + tamper tests |
| Reliability | `workflow/dlq`, `core/middleware` | circuit breaker, stale recovery, DLQ, rate limit |

Run the Phase 11 suite + demo:
`pytest tests/test_security_phase11.py`, `python -m scripts.seed_security_governance`.
