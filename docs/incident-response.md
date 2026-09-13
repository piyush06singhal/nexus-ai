# NEXUS — Incident Response

Runbook for responding to security/governance incidents using the Phase 11
incident model. It is deliberately *defensive*: NEXUS does **not** perform
autonomous remediation — a human decides, an explicit containment action (or
two) applies, everything is audited.

---

## 1. The incident lifecycle

```text
SECURITY_SCANNER / THREAT RULES
        │  (SecurityEventService → ThreatDetectionService)
        ▼
DETECTED ──► INVESTIGATING ──► CONTAINED ──► RESOLVED ──► CLOSED
   │              │               │              │
   ▼              ▼               ▼              ▼
 security_events  + timeline +   + containment   + resolution note
                  alerts          actions (audited)
```

`IncidentService` persists `incidents` with status
(`detected → investigating → contained → resolved → closed`), a timeline of who
did what when, linked alerts, and an audit trail. `IncidentActionExecutor`
applies the §85 containment actions.

### Statuses
- **detected** — a rule or alert tripped; triage required.
- **investigating** — analyst confirms scope; timeline updated.
- **contained** — the blast radius was cut (below). No further spread allowed.
- **resolved** — root cause handled, evidence preserved.
- **closed** — post-incident review recorded; optional retention of artifacts.

---

## 2. Roles (separation of duties)

| Role | Responsibilities | System role (RBAC) |
|---|---|---|
| **Analyst** | Triage, investigate, contain | `security.manage`, `incidents.read` |
| **Approver** | Authorize containment + break-glass | `incidents.contain`, `approvals.approve` |
| **Operator** | Execute approved actions | `governance.manage`, `incidents.manage` |
| **Auditor** | Verify audit chain, no same-person SoD | `audit.read` |

Phase 11 enforces **self-approval blocked** and, by default, **separation of
duties** on approval gates: the requester cannot be the approver
(`ApprovalGovernance`). Break-glass overrides approve only with a reason, a
time limit, and full audit.

---

## 3. Containment actions (§85) — all audited

`IncidentActionExecutor.execute(incident_id, action_code, params)` returns an
`incident_action` record (state `applied`/`failed`, rationale, result); every
action is written to the audit chain.

| Code | Effect | When |
|---|---|---|
| `pause_company` | Kill switch COMPANY scope for the tenant | tenant-wide suspicious activity |
| `disable_external_actions` | Kill switch EXTERNAL scope | suspected exfiltration / external misuse |
| `disable_agent` | Kill switch AGENT scope (or the one agent) | compromised/runaway agent |
| `disable_integration` | Suspend the Phase 10 integration | abused provider connection |
| `revoke_credential` | Revoke a Secret (external creds are ref-only) | credential suspected compromised |
| `suspend_employee` | Suspend the employee/agent identity | insider signal |
| `terminate_browser_session` / `terminate_computer_session` | End the session row | active misuse of the surfacing tool |

Each `_action_*` returns a result dict (e.g. number paused, session ids
terminated); a failure marks the `incident_action` `failed` and is audited
too.

---

## 4. Runbook: 7 scenarios

### 4.1 Cross-company access spike
1. **Signals** — repeated `CROSS_COMPANY_ACCESS` events near one `actor_id`;
   alert via `SecurityAlertService`.
2. **Triage** — confirm the identity's `company_id` and whether the target was
   genuinely foreign.
3. **Contain** — `suspend_employee` (the identity) immediately; if it looks
   like a stolen token, `revoke` the session (logout) — that's a `sessions`
   revoke, then rotate the affected secret(s) if touched.
4. **Verify** — `GET /api/v1/security/audit/verify` shows chain intact; no
   row escaped within the tenant's boundary.
5. **Resolve/close** — note the false positive or damaged surface; reopen rules
   tuning if needed.

### 4.2 Credential exposure
1. **Signals** — `SECRET_ACCESS_DENIED`, `DATA_EXFILTRATION_BLOCKED`, redaction
   filter trips in observability.
2. **Contain** — `revoke_credential` (revoked ⇒ reads fail), then `rotate`
   re-issues through `SecretManager` with a fresh keygen; kill switch
   `disable_external_actions` while you assess blast radius.
3. **Verify** — secret read now throws; ciphertext unchanged (key rotation is
   `key_id` lineage); any earlier plaintext in logs is gone via the redaction
   filter.
4. **Close** — record rotation hash/ids.

### 4.3 Prompt-injection detected
1. **Signals** — `PROMPT_INJECTION` event from an untrusted observation.
2. **Triage** — verify which source fed it (`source_type`/`resource_ref`).
3. **Fence** — add a `context_authorities` entry downgrading the source
   authority; keep suggestions as data; no secrets were exposed (asserted by
   the detector test).
4. **Close** — record the intercepted payload fingerprint.

### 4.4 A tool tries to escalate itself
1. **Signals** — `ToolSecurityError` DENIED tool record / `tool_security_denied`
   warning log.
2. **Action** — deny-list the tool (`ToolSecurityPolicy(deny_tools=…)`), check
   the agent's prompt didn't instruct it.
3. **Verify** — re-run: call denied at step 3.5, recorded as DENIED.
4. **Close** — note the blocking name/arg-key pattern.

### 4.5 Provider outage (external dependency)
1. **Signals** — circuit breaker OPEN, `/health/dependencies` red, jobs to DLQ.
2. **Triage** — breaker snapshot (`consecutive_failures`, state).
3. **Contain/rest** — let the breaker HALF_OPEN probe; failed jobs are in
   `dead_letter_jobs` (nothing silently lost), replay after recovery.
4. **Verify** — `/health/ready` + a green dependency probe; DLQ drained and
   re-queued.
5. **Close** — record outage window and replayed job count.

### 4.6 Runaway workload
1. **Signals** — `RESOURCE_EXCEEDED` event / `RunawayGuardStopped`.
2. **Contain** — `disable_agent` (that agent) + tighten `resource_limits`.
3. **Verify** — restart the workload within budget.
4. **Close** — output usage summary from `ResourceGovernanceService.usage_summary`.

### 4.7 Break-glass activation
1. **Require** — incident in `investigating`; written justification.
2. **Activate** — `break_glass_access` (reason, scope, `max_minutes`).
3. **Supervise** — the temporary elevation auto-expires; every action audited
   under the incident id.
4. **Close** — revoke early if no longer needed.

---

## 5. Escalation rules (ThreatDetectionService)

Configurable rules count events in a window and raise `security_alerts`
(severity LOW→CRITICAL) which mirror to Phase 8 `AlertManager`. Examples:
- **N failed logins** on one account in a window → `AUTH_ANOMALY`.
- **Repeated denied tool calls** for one agent → `SUSPICIOUS_ACTIVITY`.
- **Cross-company attempts** repeated → `CRITICAL` isolation concern.
- **Large unusual external activity** in a window → `EXTERNAL_ANOMALY`.

An alert can be `acknowledge`d (ownership) and `resolve`d (note required);
incidents attach alerts and their timeline.

---

## 6. Demo / drill

```bash
cd apps/api
DATABASE_URL="sqlite:////tmp/nexus_secdemo.db" \
  .venv/bin/python -m scripts.seed_security_governance [--reset]
```

Runs the seven attacks (each blocked + recorded), the failure-recovery drill
(circuit breaker), and verifies the audit hash chain stays intact. Use it as an
onboarding drill: one volunteer reads out the attack, one person answers with
the runbook section above.
