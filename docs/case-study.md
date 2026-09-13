# NEXUS — Case Study

## 1. Problem

Traditional AI assistants are stateless chatbots: answer a prompt, forget it
next turn. A business objective is not a single prompt. It requires memory,
multi-step tool use, governed autonomy, reliability, auditability, and
organizational structure (departments, employees, budgets, approval gates).

Real autonomy requires a verification/recovery loop, not "hope the model is
right." A multi-agent team requires orchestration, not independent calls. A
company requires governance, not raw API access. And any optimization or
simulation that might affect operations must be labeled honestly and gated
behind human approval.

## 2. Why Chatbot Architectures Are Insufficient

| Gap | What a chatbot does | What real autonomy needs |
|-----|--------------------|-----------------------|
| State | Stateless per prompt | Persistent memory (5 types), context injection |
| Tool use | Optional, unbounded | Permission-gated registry, tool-calling loop, persisted tool calls |
| Multi-step | Single LLM call | Workflow engine with dependency-ordered steps, retry, timeout |
| Multi-agent | None | Planner → Selector → Orchestrator → Synthesizer |
| Verification | None | Verify correctness, then bounded self-healing |
| Recovery | None | Escalate unfixable failures, record what happened |
| Governance | None | Approval gates, kill switches, resource limits |
| Audit | Logs only | Append-only hash-chained audit log (tamper detection) |
| Organization | None | Companies, departments, KPIs, budgets, policies |
| What-if | None | Sandboxed simulation (SIMULATED/FORECAST, never ACTUAL) |
| Marketplace | None | Internal, metadata-only, approval-gated install |
| External access | Direct (dangerous) | Governed funnel: risk → policy → approval → exec → verify → recover → audit |

## 3. NEXUS Architecture

NEXUS composes 12 layers, each building on the ones below.

### Runtime

`validate → build_context → generate → tool_calls? → (execute tool, feed
result back, repeat) → parse → persist AgentExecution`

The `MockProvider` returns deterministic JSON; real providers (OpenAI/Anthropic)
are registered behind the same abstraction.

### Tools

`PermissionService` gates every tool action. Built-in tools: `calculator`,
`datetime`, `file_read`, `web_search`. External integrations register as
additional tools at runtime.

### Workflows

Steps: `AGENT_TASK`, `TOOL_ACTION`, `CONDITION`, `DELAY`. The engine
topo-sorts them, runs in dependency order, and records a step trace. A
DB-backed worker (`workflow_queue` table, heartbeat, DLQ) and scheduler
drive execution.

### Memory

5 types (working / episodic / semantic / procedural / knowledge), namespace
isolated. Hybrid retrieval (semantic + keyword + recency + importance).
Auto-extracted from completed executions. Injected into the agent's context.

### Orchestration

A deterministic planner decomposes the goal into tasks. A capability-based
selector assembles a team. The orchestrator runs tasks in parallel +
dependency order over an authorized message bus. A synthesizer aggregates
results with conflict detection and source attribution.

### Verification / Recovery / Evaluation

Verify correctness → recover bounded failures (configurable budgets: `max_retries=2`,
`max_runtime_seconds`, `tool_call_budget`) → escalate the rest. Post-execution
evaluation detects regressions.

### Employee OS

Identity, skills, goals, workload management, assignment engine, performance
tracking, templates, audit logging. Each employee is a persistent entity with
capacity limits and budget.

### Company Layer

Companies → departments → org chart, KPIs (computed from authoritative data),
budgets (company → department hierarchy), policies (most-restrictive-wins),
decisions (with audit trail), risks, alerts, health scoring.

### Autonomous Startup Engine

Mission → strategic plan → startup plan → company bootstrap → operating
cycles → feedback → replan. Human approval gates. Bounded autonomy:
`ApprovalGateManager` decides; the system proposes.

### External Integrations & Computer Use

Integrations register as permission-gated tools. Every external action flows
through `risk → policy → approval → execution → verification → recovery →
audit`. Credentials are reference-only (env-sourced, never in DB). Browser
and computer sessions are bounded and simulated; observations are labeled
UNTRUSTED.

### Security / Governance (Phase 11)

Fernet AES-256-GCM secrets, HS256 auth, RBAC/ABAC, policy engine,
append-only hash-chained audit, 13-category detection → alerts → incidents,
kill switch, resource limits, telemetry/metrics/redaction.

### Simulation / Optimization / Marketplace (Phase 12)

- **Simulation**: deterministic sandbox, seeded Monte-Carlo on demand,
  digital-twin snapshots, baseline-vs-scenario comparisons. All outputs
  labeled SIMULATED or FORECAST.
- **Optimization**: multi-objective (greedy / exhaustive / ranking),
  rejects policy/budget-violating candidates, ships a 10-part
  explainability block behind an ApprovalGateManager gate.
- **Marketplace**: internal, metadata-only, `PackageScanner`, evidence-based
  recommendations (real benchmark scores), approval-gated install.
- **Closed loop**: OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE →
  EXECUTE → MEASURE → LEARN. References only; reuses Phase 9 gates +
  Phase 11 budgets.

## 4. Results

| Metric | Value |
|--------|-------|
| Backend tests | 1085+ across 94 files |
| Frontend tests | 141 |
| Database tables | 43 additive Phase 12 tables; 90+ total |
| CI pipeline | Backend (ruff, pytest, migration round-trip) + Frontend (lint, tsc, vitest, build) + Docker build |
| Per-day resource budgets | 8 Phase 12 categories governed by Phase 11 limits |
| Seed scripts | 5, dependency-ordered, idempotent, `--reset` safe |
| Perf baseline | `python -m scripts.perf_baseline` — dev-environment measurements only |
| Health probes | Unauthenticated `/api/v1/health/{live,ready,dependencies}` — compose healthchecks |

## 5. Limitations (Honest)

Per §48 — these are not bugs to be fixed; they are design boundaries:

- **No real LLM deployment.** All tests use `MockProvider` (deterministic
  double). Real providers are registered but exercised only via API keys
  in the environment; no managed deployment exists.
- **No production history.** The demo runs on local Docker or SQLite.
  Postgres + Redis are present but not configured for production durability,
  replication, or failover.
- **Dev-environment measurements only.** Perf numbers are on SQLite +
  MockProvider (no network, no real model latency). Not SLAs.
- **No compliance certifications.** SOC2, HIPAA, FedRAMP, and similar
  require independent audits. NEXUS implements the *controls*; it does not
  claim the *certifications*.
- **Simulation outputs are forecasts.** All simulation outcomes are labeled
  SIMULATED or FORECAST. They are never treated as commitments or actuals.
- **Optimization proposes; governance decides.** Every recommendation
  requires an approval gate. There is no auto-production-replacement.
- **No self-modification / RL.** The system does not learn by modifying
  its own code, weights, or policies without an audited, governed,
  human-approved process.
- **Marketplace is internal.** Packages are metadata-only references
  benchmarked against the Phase 12 engine. There is no public ecosystem
  or package registry.
- **Simulated browser/computer.** External integration sessions are
  sandboxed simulations, not real network calls.

## 6. Future Research Directions

- **Real LLM cost tracking.** Token usage is recorded; cost estimation
  needs production pricing data.
- **Distributed workers.** The DB-backed queue is simple; a distributed
  system (Celery, BullMQ, Temporal) would improve throughput.
- **Real browser sessions.** Playwright integration to replace the
  simulated browser.
- **External connectors.** Slack, Google Workspace, Jira, GitHub
  connectors replacing the env-based stubs.
- **Edge deployment.** Agent inference at the edge for latency.
- **Marketplace federation.** Cross-organization package sharing.
- **Full observability stack.** OpenTelemetry traces → Grafana dashboards.
- **PostgreSQL RLS.** Row-level security as an additional isolation layer.
- **Managed secrets.** Vault / KMS integration replacing env-sourced keys.
