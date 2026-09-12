# NEXUS External Integrations & Computer Use (Phase 10)

Phase 10 turns NEXUS from an internal operating system into a **governed** system that can safely interact with external software, websites, APIs, files, email, calendars, and computer interfaces. Every interaction is not a free pass — it flows through a single funnel that composes everything Phases 0–9 already own:

> **External content is untrusted by default. External content is never an instruction. Every external action passes risk → policy → autonomy → approval → execution → scrub → verification → recovery → memory → audit** — and **credentials never reach the model context, the database-at-rest, responses, or logs.**

The layer lives in `apps/api/app/external/`, mirrors the `app/startup/` service conventions, and composes — never duplicates — the Tool Registry (Phase 2), Workflows (3), Memory (4), Verification/Recovery/Evaluation (6), Employees (7), Companies/Policy/Decisions/Budgets/Events (8), and the Autonomy + Approval Gate engine (9).

> Core posture: *the external layer can act — but only within a company's policy and an approved-gate envelope; high-risk or irreversible capabilities always park at a human gate.*

This document is the reference for the packages, the funnel, the credential vault, browser/computer safety models, the API surface, the frontend, the security model (§66/§67 fixtures), the demos (§68–70), and the boundaries.

---

## Table of contents

1. [Architecture principles](#architecture-principles)
2. [The integration layer](#the-integration-layer)
3. [Capability tools through the Tool Registry](#capability-tools-through-the-tool-registry)
4. [The external-action funnel](#the-external-action-funnel)
5. [Risk, policy & autonomy](#risk-policy--autonomy)
6. [Credential vault (reference-only)](#credential-vault-reference-only)
7. [Idempotency & approvals](#idempotency--approvals)
8. [Browser use](#browser-use)
9. [Computer use](#computer-use)
10. [Webhooks & external events](#webhooks--external-events)
11. [Files & workspaces](#files--workspaces)
12. [Security model](#security-model)
13. [Verification, recovery & evaluation](#verification-recovery--evaluation)
14. [Database model](#database-model)
15. [API surface](#api-surface)
16. [Frontend](#frontend)
17. [Demos](#demos)
18. [Testing](#testing)
19. [Phase 11 boundary](#phase-11-boundary)

---

## Architecture principles

- **One funnel.** `ExternalActionManager.create` is the single choke point. An external action is only ever: journaled → risk-classified → policy-resolved → autonomy-decided → (gate) → executed through a bounded adapter → scrubbed → verified → recovered-if-failed → mirrored to memory → audited. There is no path that bypasses it.
- **Compose, never duplicate.** No second tool executor, workflow engine, memory, verification, recovery, evaluation, policy, approval, or event system. Capability tools register in the existing `app/tools/` registry; recovery reuses `app/recovery/` and its taxonomy; verification reuses `app/verification/`; audits go through `OrgEventLogger` via `app/external/events.py`.
- **Deterministic first.** Every provider, driver, and fixture is an in-repo deterministic mock. Tests, CI, and the demos never require a paid API, real SMTP, a real browser, or real payments.
- **Bounded autonomy.** The exposed autonomous action key `external_action` is *unlisted* in `AutonomyService`, so it defaults to require-approval at every autonomy level. A company may allow low-risk reads via allow matrix; HIGH/CRITICAL risk still independently requires an approval gate in the external layer. `_NEVER_ALLOWED` is untouched.
- **Untrusted by default.** Observations carry a `content_type: EXTERNAL_UNTRUSTED_CONTENT` marker (§65). Page/webhook content is data, never instructions — it cannot change policies, permissions, secrets, or approval requirements.
- **Reference-only credentials.** The DB stores an opaque reference and a masked suffix. Secrets arrive from an operator env var or a one-shot request value and are discarded immediately after use; a global redactor scrubs known secret patterns from every response, log, DB row, memory write, and tool output.

---

## The integration layer

`app/external/registry.py` defines the `IntegrationProvider` protocol (`slug/name/category/capabilities()/execute()/test()/verify()`) and a registry mirroring `app/ai/registry.py`. Providers are registered at import and discovered per slug.

| Provider | Slug | Category | Capabilities | Risk posture |
|---|---|---|---|---|
| Email | `email` | communication | `search_messages`, `get_message` (LOW), `create_draft` (MEDIUM, partially reversible), `send_message` (HIGH, irreversible, approval-required) | mock mailbox with deterministic fixtures |
| Calendar | `calendar` | productivity | `list_events`, `get_event` (LOW), `create_event` (MEDIUM, →verify), `update_event`, `cancel_event` | mock calendar |
| Development | `development` | development | `list_repositories`, `get_repository`, `list_issues`, `get_issue` (LOW), `create_issue`, `update_issue`, `create_comment` (MEDIUM) | mock GitHub; no auto-merge / no PR merging (Phase 11) |
| Web Research | `web_research` | web | `search_pages`, `open_page`, `extract_text`, `summarize_text` (LOW) | bounded fixture pages, size-capped |
| Generic HTTP Connector | `http_connector` | custom_api | adapter-driven GET/POST/PUT/DELETE | **disabled by default** (`external_generic_http_connector_enabled=False`); admin-gated, domain-allowlisted, rate-limited, approval-controlled (§14) |

An **integration** is a company-scoped instance of a provider; its **capabilities** materialize into DB rows (`integration_capabilities`) with risk level, reversibility, idempotency support, `approval_required`, required permissions/scopes. A **connection** binds a credential reference to scopes/permissions and carries a lifecycle (`CONNECTED/DISCONNECTED/ERROR/REVOKED/EXPIRED`).

Enum surfaces: `IntegrationCategory` (communication … custom_api), `AuthMethod` (`api_key/basic/oauth/none`), `IntegrationStatus` (`available/configuring/connected/disconnected/error/suspended/revoked`), `ConnectionStatus`, `RiskLevel` (`low/medium/high/critical`), `Reversibility` (`reversible/partially_reversible/irreversible/unknown`).

For details on the workflow integration, see [Workflow & orchestration](#api-surface) — an `EXTERNAL_ACTION` workflow step (`WorkflowStepType.EXTERNAL_ACTION`) runs one governed capability as a step, reusing the Phase 3 engine.

---

## Capability tools through the Tool Registry

Per §86 Rule 4, every provider capability is also a **tool in the Phase 2 registry**: name `{provider}.{capability}` (e.g. `email.search_messages`, `devplatform.create_issue`, `browser.page_action`, `computer.action`, `web.search`). `app/external/tools.py -> register_capability_tools()` builds a `BaseTool` per capability at import:

- `dangerous=True` for HIGH/CRITICAL capabilities, so an agent needs explicit permission (`check_permission`) before the funnel is even entered.
- The tool forwards to `ExternalActionManager.create`, so the *same* risk/policy/approval/verification/audit funnel governs agent-driven and direct-demo calls.
- There is **no raw `http_request` tool by default**; the generic connector is opt-in per company, per domain, and still gated.

This is why an agent *did* external work, a workflow step, an orchestration task, and a direct API demo all produce identically-governed journal rows.

---

## The external-action funnel

`ExternalActionManager.create(...)` (aliased through `app/external/action.py`) implements, in order:

```
 REQUESTED → idempotency check (company, integration, capability, idempotency_key)
           → risk classification (capability default → integration_policies override → escalation)
           → ExternalPolicyResolver (most-restrictive-wins: Phase 8 PolicyResolver + integration_policies + domain_allowlists)
           → AutonomyService.decision("external_action") [BLOCK → blocked; REQUIRE_APPROVAL | HIGH | CRITICAL → gate]
           → parked AWAITING_APPROVAL with EXTERNAL_ACTION_APPROVAL approval gate (unless approved_gate_id replayed)
           → EXECUTING via adapter (timeout-bounded, size-capped)
           → result scrub (no secrets, no untrusted-payload elevation)
           → optional verification (VerificationService)
           → recovery on failure (classify → Phase 6 taxonomy → RecoveryService/backoff, idempotency-protected)
           → memory candidate (MemoryService; secrets never stored)
           → SUCCEEDED/FAILED + OrgEventLogger audit
```

**Allowed call routes.** `create` accepts either no gate (fresh action; will gate itself if required) or an `approved_gate_id` that was previously created and **human-approved**. Rule 12 (one gate → one action → once) is enforced at the DB level and at replay: a consumed gate raises `gate_used` / returns 409.

**Decision knives.**

| Level | What it means | Example |
|---|---|---|
| `low` | auto-runs if policy allows; no approval | `email.search_messages`, `calendar.list_events` |
| `medium` | auto-runs if approved in policy (default require-approval because unlisted) | `email.create_draft`, `devplatform.create_issue`, `calendar.create_event` |
| `high` | **always** requires a gate even with allow matrix | `email.send_message`, any `approval_required` capability |
| `critical` | requires a gate + is reviewed by the op center | (reserved; mapped in `risk.py`) |

**Cancellation.** `cancel` transitions an `awaiting_approval` (or `requested`) action to `cancelled`; terminal actions cannot be cancelled.

**Timeouts, limits.** Settings bound everything: per-action timeout (`external_action_timeout_seconds`), payload size caps, per-company journal ceiling (`max_external_actions`), provider rate limits, and a circuit breaker for the generic connector and HTTP client.

---

## Risk, policy & autonomy

- **Risk classifier** (`app/external/risk.py`) computes the effective risk: capability default → `integration_policies` override → input/action-type escalation. A `send_message` with a large recipient list or a file-upload draft escalates.
- **External policy resolver** merges Phase 8 `PolicyResolver.effective(...)` with `integration_policies` (allowed/deny per capability pattern, `risk_level_override`, `require_approval`, rate limits, budgets) and `domain_allowlists` (`ALLOW/BLOCK` per domain with methods/paths). Most-restrictive-wins.
- **Autonomy** (`app/startup/autonomy.py`) is untouched structurally. `external_action` is unlisted ⇒ `REQUIRE_APPROVAL` at every level by default. To auto-run low-risk reads a company `PUT`s an allow matrix `{"external_action":"allow"}`; HIGH/CRITICAL still require an independent gate in the external layer — the `high_risk_stays_gated_even_with_allow_matrix` test pins this.

---

## Credential vault (reference-only)

`app/external/credential.py -> CredentialVault` and the `external_credentials` table store **no plaintext**:

- `create_reference(provider, kind, masked_value)` persists only an opaque `reference`, a `masked_value` (e.g. `api-key  •••• 4321`), scopes, and an optional `env_var_hint`.
- `resolve(reference)` reads the secret at use-time from an operator env var named after the hint (e.g. `INTEGRATION_EMAIL_API_KEY`) — or from a request-supplied one-shot value that is consumed and discarded, never persisted.
- Connections carry only the reference. Test/dev flows use one-shot values; production secrets belong to the operator environment (documented in `.env.example`). This is the deliberate Phase-10 abstraction (§6); a dedicated secrets-manager integration is listed in the Phase 11 boundary.

The global `redact_secrets()` scrubber is applied to responses, result scrubbing, memory writes, tool output, and event payloads. Tests assert secret absence in every leak-prone surface (§75 Security).

---

## Idempotency & approvals

- **Caller idempotency.** `idempotency_key` (per company+integration+capability) plus a generated `external_operation_id`. A duplicate `succeeded` replay is rejected (`duplicate`, 409) — the single-send test asserts exactly one email ever leaves the mock mailbox.
- **One-gate-one-action-once.** An approval gate is created per gated action. The human approves; the caller replays with `approved_gate_id`; the gate is consumed. Any second use of that gate is rejected (`gate_used`, 409). Journal rows for the original pending action, the replay, and the blocked attempt are all immutable and linked via `correlation_id`.

---

## Browser use

`app/external/browser/` — a **provider-agnostic** `BrowserDriver` protocol with a deterministic, in-repo `MockBrowserDriver`. No Playwright, no real network, no real screenshots (Phase 11).

- **Sessions** (`browser_sessions`) are long-lived and bounded: `max_browser_sessions` per company, `max_browser_actions` per session, `max_browser_navigations`, `max_browser_session_duration_minutes`. Lifecycle `created → active ⇄ paused → completed | failed | terminated`.
- **Actions** (`browser_actions`): `open_page`, `navigate`, `back`, `forward`, `refresh`, `click`, `type`, `select`, `scroll`, `wait`, `extract_text`, `extract_links`, `screenshot`. Targets are element `#id`/label selectors on the fixture pages; `open_page`/`navigate` take a fixture URL.
- **Observations** (`browser_observations`): every observation is a *structured, size-limited* snapshot (`MAX_PAGE_SIZE`), tagged `content_type: EXTERNAL_UNTRUSTED_CONTENT`, carrying visible text, interactive elements, links, page state, and a `screenshot_ref` placeholder (never real image contents).
- **Domain policy.** Sessions resolve against `allowed_domains` + `domain_allowlists`; requests to unlisted/blocked domains are refused (`BLOCKED_DOMAIN`).
- **Sensitive interactions.** Anything resembling payment, purchase, submit, delete, publish, private-data upload, or settings change is HIGH and routed to an approval gate (§26–27) — even if an allow matrix exists.
- **Prompt injection (§66).** The fixture catalog includes a deliberately adversarial page whose content attempts to change policy/secrets/approval. Navigation to it is allowed but is *observed* as untrusted data; the test asserts the injected instruction is never carried into results, memory, or policy. Mock fixtures live in `mock_driver.py._PAGE_CATALOG` and include the `discovery.nexus.test` research catalog and the `malicious-injection` page.

A `browser` integration (category `browser`) bundles Driver + session management; agents act through `browser.page_action`.

---

## Computer use

`app/external/computer/` — same design as browser: a `ComputerDriver` protocol + deterministic `MockComputerDriver` simulating a desktop ("nexus-desk") with a bounded set of windows (reports, composer, checkout), a cursor, and deterministic responses.

- **Sessions** (`computer_sessions`): `max_computer_sessions`, `max_computer_actions`, `max_computer_session_duration_minutes`.
- **Actions** (`computer_actions`): `move_mouse`, `click`, `double_click`, `type`, `key_press`, `scroll`, `drag`, `screenshot` (ref placeholder), `wait`.
- **Sensitive path (§67).** The desktop includes a checkout window with a "Confirm purchase" flow plus `sensitive` card/CVV fields. Any action targeting the purchase path (`submit_payment`, a click on `purchase`/`sensitive` elements, `enter` in a sensitive window) is HIGH ⇒ parks at an `EXTERNAL_ACTION_APPROVAL` gate (`blocked_pending_approval`); the simulator **never performs payments**. Typing into a sensitive field returns `typed: "••••"` — never the value.
- **Observations.** `computer_observations` snapshots the desk state (windows, elements, cursor); results and snapshots are untrusted data.

---

## Webhooks & external events

`external_events` is a normalized, company-scoped entity (source/integration/event_type/payload/size/timestamp/verification/signature/correlation/dedupe). `POST /webhooks/{provider}/events` requires:

- **Signature** — HMAC with `external_webhook_hmac_secret` (~`X-NEXUS-Signature`). No secret configured ⇒ 503.
- **Timestamp window** against replay. **Replay protection** via event id dedupe (idempotency). **Size cap** (`max_webhook_payload_bytes`) and **rate limiting**.
- **Never trusted.** A verified webhook becomes a journaled event (and possibly a verification-trigger); unauthenticated payloads are never executed as instructions.

---

## Files & workspaces

`app/external/files/` provides a `WorkspaceFileProvider`:
- **Virtual workspace** (default, when `external_workspace_root` is empty) — deterministic in-repo file catalog used by demos/tests.
- **Sandboxed local workspace** — an operator-configured root with resolved-path containment, type/size/MIME validation, and a blocklist for credential/system directories. Path-traversal and arbitrary-access protections are unit-tested. The host filesystem is never exposed raw.

---

## Security model

1. **SSRF** — `app/external/api/ssrf.py` blocks loopback, private, link-local, and cloud-metadata ranges by default; every redirect hop is re-validated; DNS resolution where practical. Applies to the `SecureHTTPClient` and the generic connector.
2. **Data exfiltration** — `app/external/security/exfiltration.py` classifies data (public/internal/confidential/restricted/secret). Outbound payloads may only carry data at or below `external_outbound_class` (default `confidential`); secret/sensitive data is blocked without an explicit gate.
3. **Prompt injection (§66)** — untrusted observations are labeled (`EXTERNAL_UNTRUSTED_CONTENT`); page/webhook content cannot mutate policy, permissions, secrets, or approval requirements. A malicious-injection fixture page and test pin the invariant.
4. **Credential hygiene** — reference-only vault, masked rendering, global redaction; secret-absence assertions across response/log/DB/memory/tool output.
5. **Cross-company isolation** — every read and action is company-scoped; foreign companies get 404.
6. **Businrule limits** — `MAX_*` settings cap actions, sessions, pages, payloads, events, and workers; default-on protections (`ssrf_protection_enabled`, `prompt_injection_protection_enabled`) can be toggled but default to safe.

---

## Verification, recovery & evaluation

- **Verification** — `app/external/verification/helpers.py` wraps `VerificationService.verify_data` in capability-specific helpers (created/updated/deleted, message sent, event created, issue created, page state, expected text). Every succeeded external action and browser/computer action carries a `verification` JSON (e.g. `{"verified": true}` for `send_message`).
- **Recovery** — `app/external/recovery/mapping.py` translates external failures to the existing Phase 6 taxonomy (429 → `RESOURCE_LIMIT`, 401 → `PERMISSION_FAILURE`, 5xx → `SYSTEM_FAILURE`, timeout → `TIMEOUT`, missing element → `VALIDATION_FAILURE`). Retry uses the existing `RecoveryService`/backoff under idempotency protection — no second taxonomy, no ungoverned retries.
- **Evaluation** — `app/external/evaluation/metrics.py` aggregates §61 metrics from `external_actions`/`external_events` (success, verification, recovery, browser/computer, duplicate, intervention, duration rates) over the existing Phase 6 evaluation runner.

---

## Database model

Migration `0012_external_integrations` (additive; VARCHAR `StrEnum`s, JSON text columns, UUID PKs, `company_id` FK + indexes; `approval_gate_id` FK reuses the existing `approval_gates`).

Tables: `external_integrations`, `integration_connections`, `integration_capabilities`, `external_credentials` (no plaintext column), `external_actions` (immutable journal + attempts via `external_action_attempts`), `external_events`, `browser_sessions`, `browser_actions`, `browser_observations`, `computer_sessions`, `computer_actions`, `computer_observations`, `integration_policies`, `domain_allowlists`.

New `ApprovalGateType.EXTERNAL_ACTION_APPROVAL` is a **python-only** enum value (VARCHAR storage) — no gate migration.

---

## API surface

Routers under `/api/v1` (company scoping is a **path segment** for Phase 10 entity groups, consistent with its `?company_id=` reads everywhere 404-isolated):

| Router | Operations |
|---|---|
| `/integrations` | `POST/GET /{company_id}`; `GET/DELETE /{company_id}/{id}`; `GET /{id}/capabilities`; `POST/GET /{id}/connections`; `POST /{id}/connections/{conn}/test` and `/revoke`; `GET /{company_id}/policies` and `/domains` |
| `/external-actions` | `POST /{company_id}` (create/execute through gate or auto), `GET` (journal), `GET /{id}`, `POST /{id}/cancel`, `GET /{company_id}/dashboard` (aggregates + pending approvals) |
| `/browser/sessions` | `POST` create, `GET`, `GET /{id}`, `POST /{id}/actions`, `/pause`, `/terminate`, `GET /{id}/observations` |
| `/computer/sessions` | same verbs as browser |
| `/external-events` | `GET /{company_id}`, `GET /{company_id}/{id}` |
| `/webhooks` | `POST /{provider}/events` (signature verify, timestamp window, replay/dedupe, size cap, rate limit) |

Integration with the rest: `WorkflowStepType.EXTERNAL_ACTION` step in the Phase 3 engine (config: capability/integration/connection/input, optional `approved_gate_id`); approvals reuse `/autonomy/{company}/approval-gates` (`EXTERNAL_ACTION_APPROVAL` type); audit events write through `OrgEventLogger`.

---

## Frontend

Route group `src/app/(external)/` behind an `ExternalShell` context (company selector mirroring `StartupShell`):

- `/integrations` — dashboard: stats, add-integration form, pending external-action approvals (Approve/Reject reusing the gate API), integration cards, recent events, governance help.
- `/integrations/[id]` — capabilities (risk/reversibility/approval-required), connections (test/revoke), connect form (`auth_method` + one-shot secret or `INTEGRATION_*_SECRET` hint), latest actions.
- `/integrations/connections` — all credential bindings; only `credential_reference` is rendered, never a secret.
- `/integrations/actions` — immutable journal with expandable per-action timeline (§52: requested → risk → policy → approval → result → verification → recovery → error, plus attempts).
- `/integrations/events` — event feed with verification/signature status and payload detail.
- `/browser` + `/browser/sessions/[id]` — sessions table + detail with action runner (fixture URLs, element selectors), observations labeled EXTERNAL_UNTRUSTED_CONTENT, screenshot refs shown as placeholders (never real images).
- `/computer` + `/computer/sessions/[id]` — sessions table + detail with action runner, live window chip-map (purchase/sensitive elements highlighted), cursor, observations; high-risk elements require an approved gate id before the driver runs.

`StatusBadge` gains Phase 10 statuses (connected/disconnected, risk levels, verification states, gate type `external_action_approval`, connection-test results). Screenshots and credentials are never rendered.

---

## Demos

`apps/api/scripts/seed_external_ops.py` (`python -m scripts.seed_external_ops [--reset]`) — deterministic, MockProvider, idempotent. Creates a company with research/dev/marketing employees and runs three scenarios:

1. **External Research (§68)** — a research employee opens browser sessions on the competitor catalog (`https://discovery.nexus.test/…`), extracts text/links, stores memory candidates, verifies PASS, and produces an internal comparison report.
2. **Development Operations (§69)** — a developer employee takes a new-project requirement, runs `devplatform.create_issue` (mock) + `get_issue` verification, stores memory, and updates project state.
3. **Email Approval (§70)** — a marketing employee drafts (`email.create_draft`, MEDIUM) and attempts to send (`email.send_message`, HIGH ⇒ approval-required). The `EXTERNAL_ACTION_APPROVAL` gate is created, human-approved, replayed once, verified (`sent`), and audited — demonstrating human-in-the-loop external autonomy.

---

## Testing

New external suites in `apps/api/tests/` (all MockProvider + conftest fixtures): integration lifecycle, permissions/risk/policy, the actions funnel (approval, idempotency, cancel, journal immutability), browser (domain restriction, malicious-page prompt injection §66, action/navigation limits), computer (purchase-path gate §67, session termination), webhook (signature/replay/oversize/dedupe), security (SSRF loopback/private/metadata + redirect bypass, path traversal, credential leakage, data exfiltration, cross-company), recovery (failure→taxonomy→backoff mapping, idempotent retry), verification helpers, the `EXTERNAL_ACTION` workflow step, deterministic demo, evaluation metrics — on top of the full Phase 0–9 regression. Web tests cover the Phase 10 types/API contracts.

---

## Phase 11 boundary

Phase 11 (**not started; Rule 20**) covers production hardening of this layer: a real secrets-manager backend, real Playwright/desktop automation, enterprise RBAC, secrets management, advanced governance/compliance, real SMTP/calendar/HTTP providers behind operator credentials, and SCIM-style directory sync. §83 DO-NOT-IMPLEMENT stays absolute — no unrestricted browser/computer/shell/network, no autonomous finance/banking/trading/legal/hiring/firing/payments/account-creation/deployment/cloud mutation, no CAPTCHA/auth/security-control bypass, no marketplace/simulation/self-modification.