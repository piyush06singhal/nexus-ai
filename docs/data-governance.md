# NEXUS — Data Governance

How NEXUS classifies, protects, transfers, retains, and audits its data. This is
the data side of the Phase 11 invariant chain — it composes the Phase 10
exfiltration guard (no parallel DLP) and the Phase 11 audit account (every
decision is recorded).

---

## 1. Classification model

`data_classifications` define an ordered ladder with an explicit owner and
outbound policy for each class:

```text
PUBLIC → INTERNAL → CONFIDENTIAL → RESTRICTED → SECRET
 (lowest disclosure cost)                    (highest)
```

| Class | Examples | Outbound (external) policy |
|---|---|---|
| `public`    | marketing copy, public docs | allowed to any destination |
| `internal`  | internal runbooks, org chart | no restriction by default |
| `confidential` | customer data, financials | **floor for outbound** — nothing higher goes out unflagged |
| `restricted`   | NDAs, HR records | requires approval or explicit allow-list |
| `secret`       | encryption keys, plaintext credentials | never leaves the platform |

`DataClassificationService` provides the registry (`register_classification`,
lookup by entity type + optional tenant) and defaults. `DataTransferPolicy`
evaluates a transfer: declared class → payload re-classification → outbound
floor → destination allow-list → approval-if-required. A blocked transfer is
recorded as `DATA_EXFILTRATION_BLOCKED` and surfaced in the audit chain.

> See [security-architecture.md](security-architecture.md) §5 and
> [threat-model.md](threat-model.md) T3 for how this composes the Phase 10
> `external/security/exfiltration.py` guard.

---

## 2. Secrets: never plaintext

Handled by `SecretManager` (store/retrieve/rotate/revoke/delete) over Fernet
AES-256-GCM ciphertext:

- At rest: ciphertext only in `secrets`.`ciphertext`; keys from env
  (`SECRET_ENCRYPTION_KEY`), not the DB.
- In transit/API: refs + `mask_hint` only — the API schema never serializes
  ciphertext or plaintext, asserted by tests (`test_no_plaintext_in_serialization`).
- In logs: the central redaction filter scrubs secret/PII patterns from every
  structured log line in every component.
- Revoke: reads raise `PermissionDeniedError` + a `SECRET_ACCESS_DENIED` event.
- Rotation: `secret_version` lineage with `key_id` — old keys retire gracefully,
  data is never re-encrypted in place.

---

## 3. Retention

`retention_policies` configure per entity type:

| Entity type | Policy shape | `--reset` purges? |
|---|---|---|
| executions, logs, memory, observations, tool calls, screenshots | time-scoped `hard`/`soft`/`anonymize` | yes (time-scoped) |
| **audit_events** | `retention-lock` — keep forever, never hard-deleted | **no** |
| **security_events** | `retention-lock` / configured days | **no** |

`RetentionService` = `set_policy` → `purge_due` (classifies) → `purge_execute`
(by semantics). The **audit and security event tables are excluded from
hard-delete semantics** (`_RETAINED_ENTITY_TYPES`) so the immutable record
survives any cleanup.

### Honest scope at the storage layer

`purge_execute` sweeps `agent_executions`, `tool_calls`, `memories`,
`observations` **time-scoped only** — those Phase 0–10 tables carry no
`company_id` column, so retention is applied by time window, while `company_id`
is used for policy lookup and audit provenance. Per-company physical storage
isolation remains a documented deployment item (§88 honesty rule).

---

## 4. Access

- Read/write goes through `AuthorizationService` (§7 chain) — a principal
  without the right permission or a matching company scope is denied, and the
  denial is recorded.
- The elevation ladder applies **most-restrictive-wins**: `PolicyEngine`
  composes the Phase 2 `PolicyResolver` so a lower level can never weaken a
  higher one, and can raise a data transfer to `REQUIRE_APPROVAL`.
- Controlled export: data-export endpoints exist only if
  `FEATURE_DATA_EXPORT_ENABLED=true` (default off) and respect classification
  and approval.

---

## 5. Audit account

Every governance decision — denial, approval, transfer check, retention purge,
reclassification — is written by `AuditService.record()` into the append-only
hash-chained `audit_events` (verified via `verify_chain()`). Data governance is
therefore **provable, not asserted**: you can point at the chain and show what
was blocked, allowed, approved, and purged, and detect any tampering.

---

## 6. API surface

Under `/api/v1/data`:

| Route | Purpose |
|---|---|
| `GET /data/classifications` | classification registry |
| `POST /data/transfer-check` | run `DataTransferPolicy.evaluate` (records decision) |
| `GET/POST /data/retention` | view / set `retention_policies` |

---

## 7. Verification & demo

```bash
cd apps/api
# unit proofs
.venv/bin/python -m pytest tests/test_security_phase11.py -q \
  -k "secret or transfer or retention or classification or exfiltration"

# demo (attack 7 = credential access denied, no secret exposure + audit)
DATABASE_URL="sqlite:////tmp/nexus_secdemo.db" \
  .venv/bin/python -m scripts.seed_security_governance
```
