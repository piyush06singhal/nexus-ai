# NEXUS — Agent Marketplace

What the Phase 12 agent marketplace actually delivers, how to run it, and what it
honestly does not claim. Part of the Phase 12 suite — see [phase-12.md](phase-12.md)
for the umbrella, and the sibling docs [simulation.md](simulation.md),
[optimization.md](optimization.md), [experimentation.md](experimentation.md),
[benchmarking.md](benchmarking.md), and
[closed-loop-optimization.md](closed-loop-optimization.md).

---

## 1. High-level

The marketplace (`app/phase12/marketplace.py`) is an **internal / private,
metadata-only** catalog of agent packages. A package carries *capabilities,
skills, supported task types, requirements, a security classification, versioned
releases (semver), reviews, and attached benchmark scores* — it **never** carries
secrets, credentials, private memories, execution history, tokens, or executable
payloads. `PackageScanner` statically rejects all of those at every entry point
(package create, version create, install), so nothing dangerous is ever persisted
or installed.

Install style is **safe install (§37)** — `install()` checks publish status,
re-scans the version's metadata, refuses incompatible versions, and routes any
install that `require_approval` or carries a `confidential`/`restricted`
classification through an `ApprovalGateManager`
`HIGH_RISK_ACTION_APPROVAL` gate ("marketplace.agent.install"). Confirmations are
explicit; the marketplace can never bypass RBAC/ABAC/policy/limits/secrets/audit/
approvals.

## 2. What landed

- **`MarketplaceService`** (`marketplace.py`) — `create_package` / `list_packages` /
  `get_package` / `add_version` / `list_versions` / `publish` (requires ≥1 version) /
  `deprecate` / `install` / `confirm_install` / `reject_install` / `add_review`
  (rating 1..5) / `attach_benchmark`.
- **`PackageScanner`** — returns a list of violations (empty = safe). It rejects:
  - **forbidden keys**: `secret`, `credential`, `token`, `private_memory`, `memory`,
    `execution_history`, `password`, `private_key`, `api_key`;
  - **forbidden payload keys**: `body`, `code`, `script`, `payload`, `executable`;
  - **secret-like content** — regexes for `sk-…`, `api_key`/`apikey`,
    `bearer <token>`, and PEM `-----BEGIN…`;
  - **executable-like content** — trailing executable extensions (`.py`, `.sh`,
    `.bat`, `.exe`, `.dll`, `.so`, `.ts`, `.js`, `.ipynb`) and `#!…` shebangs.
  A public `POST /marketplace/scan` endpoint exposes the scanner to tooling.
- **Package model** — `AgentPackage` (name unique per company, `status` draft →
  published → deprecated → archived, `security` classification public / internal /
  confidential / restricted, `capabilities_json`, `skills_json`,
  `supported_task_types_json`, `requirements_json` for model/tools/permissions);
  `AgentPackageVersion` (semver, changelog, `compatibility` compatible /
  compatible_with_note / incompatible); `AgentPackageCapability`,
  `AgentPackageDependency`, `AgentPackageBenchmark` (score per version), and
  `AgentPackageReview` rows.
- **Install** — `AgentInstallation` rows carry `status` (pending /
  approval_required / installing / installed / failed / uninstalled), the
  `approval_gate_id`, and `config_json`. `confirm_install` completes a `installing`
  installation to `installed`; `reject_install` fails it, recording the rejection.
- **Agent recommendations** — `AgentRecommendationEngine`
  (`app/phase12/recommend.py`) ranks *published* packages for a task using **measured
  signals only**: capability fit (+0.3 for task-type match, +0.15 per matched
  skill), the average attached `AgentPackageBenchmark` score, reliability (derived
  from capability rows), budget/latency penalties against declared requirements,
  then a reasoned rank up to 10. Scores + `reasoning`, `tradeoffs_json`
  (pros/cons), and `compatibility` are exposed per recommendation; a run defaults to
  `policy_status=pending_approval` so recommendations are gated, never applied
  directly.
- **Reputation** — `AgentReputationRecord` derives score from measurable sources
  only (`benchmark`, `success`, `verification_pass`, `recovery`, `consistency`,
  `rating`) — no self-rating or manipulation.
- **API** (`app/phase12/api/marketplace.py` + `recommendations.py`) — mounted at
  `/api/v1/marketplace` and `/api/v1/agent-recommendations` (see §4).
- **Migration** — `0014_phase12_sim_opt_mkt` adds the marketplace tables
  (`agent_packages`, `agent_package_versions`, `agent_package_capabilities`,
  `agent_package_dependencies`, `agent_package_benchmarks`, `agent_package_reviews`,
  `agent_installations`, `agent_recommendations`, `agent_reputation_records`)
  additively. `company_id` FK + index on every table — the catalog and its
  installations never leak across companies.

## 3. Governance

- **Static rejection is the load-bearing guarantee** — every create/version/install
  path re-scans metadata; a violation raises `MarketplaceError` and nothing is
  persisted. Metdata fields live in `requirements_json` under a `metadata` key so
  per-version payloads are scanned too.
- **Install is approval-gated** — `pending → approval_required → installing →
  installed`, with the gate created via `ApprovalGateManager` (`HIGH_RISK_ACTION_APPROVAL`,
  requested action `marketplace.agent.install`, module `phase12`). Installing is the
  only mutation; publishing a package merely flips status after checking a version
  exists.
- **Per-day budget** — `marketplace_ops` is a registered Phase 12 resource category
  (`governance.py`), configured through the Phase 11 resource-limit APIs.

## 4. API map

```text
# /api/v1/marketplace
POST   /marketplace/scan                       scan arbitrary metadata; {"violations": [...]}
GET    /marketplace/agents                     list packages (?company_id, ?status)
POST   /marketplace/agents                     create a package (optional initial version)
GET    /marketplace/agents/{id}                get one package
PATCH  /marketplace/agents/{id}                update description / display_name
POST   /marketplace/agents/{id}/versions       add a semver version (scanned)
GET    /marketplace/agents/{id}/versions       list versions
POST   /marketplace/agents/{id}/publish        publish (requires ≥1 version)
POST   /marketplace/agents/{id}/deprecate      deprecate
POST   /marketplace/agents/{id}/reviews        add a review (rating 1..5)
GET    /marketplace/agents/{id}/reviews        list reviews
GET    /marketplace/agents/{id}/benchmarks     benchmark scores per installed version
POST   /marketplace/install                    request install (approval-gated)
GET    /marketplace/installations              list installations (?company_id)
POST   /marketplace/installations/{id}/confirm complete an installing → installed
POST   /marketplace/installations/{id}/reject  fail the installation

# /api/v1/agent-recommendations
GET    /agent-recommendations                  list (?company_id)
POST   /agent-recommendations                  rank for a task_type (+ skills /
                                                   budget_limit / latency_limit_ms)
GET    /agent-recommendations/{id}             get one recommendation
```

## 5. How to verify

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_phase12_marketplace.py -q

# Migration round-trip (revision 0014_phase12_sim_opt_mkt)
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade 0013 && .venv/bin/alembic upgrade head

# Live smoke (server on 127.0.0.1:8000)
.venv/bin/python -m scripts.smoke_api --phase 12
```

The Phase 12 demo (Part 5) publishes a "Research Analyst Pro" package protected at
`confidential`, benchmarks it, attaches the real correctness score, publishes, gets a
rank-1 recommendation with `policy_status=pending_approval`, and opens a safe
install that lands in `approval_required` (gate created, nothing installed yet):

```bash
cd apps/api
.venv/bin/python -m scripts.seed_simulation_optimization [--reset]
```

## 6. Known honest limits

- **Metadata-only, internal/private.** There is no public internet-facing catalog,
  no executable distribution, and no credential/secret handling: packages are
  descriptions that composition workflows may use — never bundles of secrets,
  private memories, execution history, tokens, or code payloads. `PackageScanner`
  rejects those; treat any attempted bypass as a failure of the static scan, not a
  supported path.
- **Reputation comes from measurable signals only** (`benchmark`, `success`,
  `verification_pass`, `recovery`, `consistency`, `rating`). Where no benchmark or
  capability signal exists yet, the recommendation engine falls back to conservative
  base constants (0.7 benchmark / 0.6 reliability) — a floor, not a measurement.
- Feature-scope honesty: publishing is status flips, not code shipment; "installing"
  records a governed, approved installation reference in `agent_installations`
  (through the same `EmployeeManager` path) — it does not download or execute
  anything.
- Per-company marketplace budgets are DB-configured (unlimited until an operator
  sets limits through the Phase 11 governance API).