# NEXUS — AI Company Layer (Phase 8)

The Company Layer sits **above** the Employee OS and provides the organizational structure for an AI company — departments, goals, KPIs, budgets, policies, decisions, risks, alerts, health scoring, analytics, and reporting — all built on real data from Phases 1–7.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   Company Layer (Phase 8)                   │
│                                                             │
│  Company → Department → Employee → Agent → Task             │
│                                                             │
│  Goals ← parent_goal_id cascade                             │
│  KPIs ← computed from real execution/verification/budgets   │
│  Budgets ← company → department hierarchy                   │
│  Policies ← global → company → dept → employee (most        │
│             restrictive wins)                                │
│  Decisions ← draft → pending_review → approved/rejected     │
│              → implemented (audit trail)                    │
│  Risks ← severity × status                                  │
│  Alerts ← threshold detection + acknowledge/resolve          │
│  Health ← 6-dimension weighted score                        │
│  Reports ← metrics verified against source data             │
│  Analytics ← workforce/ops/finance aggregation              │
│  Events ← full timeline + audit log                         │
│  Routing ← company-aware task assignment + explainability   │
│  Delegation ← authority/capability/budget/policy verified   │
│                                                             │
└──────────────────┬──────────────────────────────────────────┘
                   │ reuses
┌──────────────────▼──────────────────────────────────────────┐
│                  Employee OS (Phase 7)                      │
│  ai_employees · employee_goals · employee_budgets           │
│  employee_reviews · employee_templates · employee_audit_log  │
└──────────────────┬──────────────────────────────────────────┘
                   │ reuses
┌──────────────────▼──────────────────────────────────────────┐
│  Agent Runtime · Workflow · Memory · Orchestration          │
│  Verification · Recovery · Evaluation (Phases 1–6)          │
└─────────────────────────────────────────────────────────────┘
```

The layer does **not** replace or modify any Phase 1–7 code. Employees are linked to companies via `organizational_memberships`; all existing employee functionality continues to work independently.

---

## Companies

A **company** is the top-level organizational entity.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `name` | string (unique) | Company name |
| `slug` | string (nullable) | URL-friendly identifier |
| `description` | string | What the company does |
| `mission` | string | Current purpose |
| `vision` | string | Long-term goal |
| `industry` | string | Industry classification |
| `values` | JSON | Company values (string array) |
| `strategic_priorities` | JSON | Current priorities (string array) |
| `status` | enum | `draft` → `active` → `paused` → `active` / `archived` (final) |
| `owner_id` | UUID (nullable) | Employee who owns the company |
| `timezone` | string | Default timezone |
| `currency` | string | Default currency (e.g., `USD`) |

### Lifecycle

```
draft ──▶ active ──▶ paused ──▶ active
                                  │
                                  ▼
                              archived (terminal)
```

Every transition is validated and logged to `organizational_events`.

### API

- `POST /api/v1/companies` — create
- `GET /api/v1/companies` — list all
- `GET /api/v1/companies/{id}` — detail
- `PUT /api/v1/companies/{id}` — update
- `POST /api/v1/companies/{id}/activate` — `draft → active`
- `POST /api/v1/companies/{id}/pause` — `active → paused`
- `POST /api/v1/companies/{id}/archive` — → `archived`

---

## Departments

Departments form a **nested hierarchy** within a company.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `company_id` | UUID FK | Owning company |
| `name` | string | Department name (unique per company) |
| `description` | string | What the department does |
| `mission` | string | Department purpose |
| `manager_id` | UUID (nullable) | Employee managing this department |
| `parent_department_id` | UUID FK (nullable) | Parent department (for nesting) |
| `status` | enum | `draft` → `active` → `paused` / `archived` |

### API

- `POST /api/v1/companies/{id}/departments` — create department
- `GET /api/v1/companies/{id}/departments` — list company departments
- `GET /api/v1/departments/{id}` — department detail
- `PUT /api/v1/departments/{id}` — update
- `GET /api/v1/departments/{id}/children` — sub-departments
- `GET /api/v1/departments/{id}/employees` — department employees
- `GET /api/v1/departments/{id}/goals` — department goals
- `GET /api/v1/departments/{id}/kpis` — department KPIs
- `GET /api/v1/departments/{id}/performance` — department performance
- `GET /api/v1/departments/{id}/risks` — department risks
- `GET /api/v1/departments/{id}/budget` — department budget
- `GET /api/v1/departments/{id}/timeline` — department events

---

## Memberships & Organization Chart

**Memberships** link employees to companies with department, role, and manager relationships. This is the integration point between the Employee OS and the Company Layer — no second employee model.

| Field | Type | Description |
|-------|------|-------------|
| `company_id` | UUID FK | The company |
| `employee_id` | UUID FK → `ai_employees` | The employee |
| `department_id` | UUID FK (nullable) | Assigned department |
| `role_id` | UUID FK → `organizational_roles` (nullable) | Assigned role |
| `responsibility` | enum | `manager` or `ic` (individual contributor) |
| `manager_id` | UUID FK (nullable) | Reports-to employee |

The **organization chart** is built recursively from departments, roles, and memberships.

### API

- `POST /api/v1/companies/{id}/memberships` — add an employee membership
- `PUT /api/v1/companies/{id}/memberships/{membership_id}` — update a membership (department/role/manager/responsibility)
- `DELETE /api/v1/companies/{id}/memberships/{membership_id}` — remove an employee from the company
- `GET /api/v1/companies/{id}/memberships` — list memberships
- `GET /api/v1/companies/{id}/organization-chart` — recursive chart tree
- `GET /api/v1/companies/{id}/employees` — all company employees

---

## Organizational Roles

Roles define authority levels and responsibilities within the company.

| `authority_level` | Description |
|--------------------|-------------|
| `individual_contributor` | Executes work within scope |
| `team_lead` | Leads a small team |
| `manager` | Manages a department |
| `executive` | Cross-company decisions |
| `company_admin` | Full company control |

### API

- `GET /api/v1/companies/{id}/roles` — list company roles
- `POST /api/v1/companies/{id}/roles` — create role
- `GET /api/v1/roles` — list global roles (filter by `company_id`, `authority_level`)

---

## Goals

Goals are **scope-discriminated** (`company`, `department`, or `employee`) and form a hierarchy via `parent_goal_id`. Company goals cascade to department goals, which cascade to employee goals — progress is computed upward from the leaf level.

| Field | Type | Description |
|-------|------|-------------|
| `scope_type` | enum | `company`, `department`, or `employee` |
| `scope_id` | UUID | The company, department, or employee ID |
| `parent_goal_id` | UUID FK (nullable) | Parent goal (for hierarchy) |
| `status` | enum | `not_started` → `active` → `at_risk` / `completed` / `failed` / `cancelled` |
| `progress` | float | 0.0 – 1.0 (computed from child goals and task evidence) |
| `owner_id` | UUID (nullable) | Employee responsible |

### Goal Tree

The API supports a **goal tree** endpoint that returns the full hierarchy:

```
Company Goal: Ship v1.0 (45%)
├── Department Goal: Ship API (20%)
│   ├── Employee Goal: Design API schema (100%)
│   └── Employee Goal: Implement endpoints (0%)
└── Department Goal: Write docs (70%)
    └── Employee Goal: Write user guide (70%)
```

### API

- `POST /api/v1/companies/{id}/goals` — create company/dept goal
- `GET /api/v1/companies/{id}/goals` — list goals (filter by `scope_type`)
- `GET /api/v1/companies/{id}/goals/tree` — hierarchical goal tree
- `GET /api/v1/goals/{id}` — goal detail
- `PUT /api/v1/goals/{id}` — update goal
- `GET /api/v1/goals/{id}/progress` — recompute and return progress
- `GET /api/v1/goals/{id}/children` — child goals
- `GET /api/v1/goals/{id}/tasks` — tasks assigned to this goal

---

## KPIs (Key Performance Indicators)

KPIs are **computed server-side only** from authoritative data sources — never user-submitted. The `KPIService` reads real tables (`tasks`, `agent_executions`, `verification_results`, `recovery_attempts`, `employee_budgets`, `goals`) and computes current values, variance, trend, and history.

### Categories

| Category | Description | Source Metric Examples |
|----------|-------------|----------------------|
| `quality` | Output quality | Average verification score |
| `productivity` | Task throughput | Tasks completed per period |
| `reliability` | System reliability | Verification pass rate |
| `cost` | Cost efficiency | Average cost per task |
| `speed` | Latency | Average execution latency |
| `goal_progress` | Goal achievement | Weighted average goal progress |
| `resource_utilization` | Resource usage | Employee utilization rate |
| `customer` | Customer metrics | (Reserved) |
| `operational` | Operations health | Success/failure ratio |

### Trend

Each KPI tracks a `trend`: `improving`, `flat`, or `declining` — computed from the latest variance against previous periods. A `history` array provides sparkline data for visualization.

### KPI Snapshot Shape

```json
{
  "id": "kpi-uuid",
  "company_id": "company-uuid",
  "scope_type": "department",
  "scope_id": "dept-uuid",
  "name": "Test pass rate",
  "source_metric": "verification_results.pass_rate",
  "category": "reliability",
  "target": 0.95,
  "current_value": 0.88,
  "variance": -0.07,
  "trend": "improving",
  "history": [
    { "value": 0.82, "trend": "declining", "recorded_at": "2026-01-31" },
    { "value": 0.88, "trend": "improving", "recorded_at": "2026-02-28" }
  ]
}
```

### API

- `GET /api/v1/companies/{id}/kpis` — list KPIs (filter by `scope_type`)
- `POST /api/v1/companies/{id}/kpis` — create KPI definition
- `POST /api/v1/companies/{id}/kpis/recompute` — recompute all KPI values

---

## Budgets

Budgets form a **hierarchy**: company budget → department budgets → employee budgets. Every execution is checked against the applicable limits.

### Budget Snapshot

| Field | Description |
|-------|-------------|
| `monthly_limit` | Maximum spend per month |
| `allocated` | Committed to planned work |
| `reserved` | Held for contingencies |
| `spent` | Actual cost incurred |
| `tokens_used` | Total tokens consumed |
| `tool_calls_used` | Total tool invocations |
| `utilization_pct` | `spent / monthly_limit × 100` |
| `remaining` | `monthly_limit - spent` |

### Enforcement Rules

1. Each execution must satisfy **all applicable limits** (company + department + employee).
2. Employees **cannot increase their own allocation**.
3. `ResourceGovernor` checks budget availability before execution and deducts after.

### API

- `GET /api/v1/companies/{id}/budgets` — company + all department budgets

---

## Policies

Policies are key-value configurations that flow through the hierarchy. The `PolicyResolver` walks:

```
global → company → department → employee → task
```

and returns the **most-restrictive** applicable value for each key. This means a department policy that says `max_retries: 1` overrides a company policy that says `max_retries: 3` — the more restrictive value wins.

### Policy Scope

| `scope_type` | `scope_id` | Description |
|---------------|-----------|-------------|
| `system` | `NULL` | Global system defaults |
| `company` | Company UUID | Company-wide policy |
| `department` | Department UUID | Department override |

### Effective Policy Response

```json
{
  "key": "max_retries",
  "value": 1,
  "source_scope": "department",
  "source_name": "Engineering policy",
  "candidates_checked": 3
}
```

### API

- `GET /api/v1/companies/{id}/policies` — list company policies
- `POST /api/v1/companies/{id}/policies` — create policy
- `GET /api/v1/companies/{id}/policies/effective?key=max_retries&department_id=...` — resolved policy

---

## Decisions

Decisions follow a review lifecycle with a full audit trail:

```
draft → pending_review → approved → implemented
                   ↓
                 rejected
```

### Decision Structure

| Field | Description |
|-------|-------------|
| `question` | What is being decided |
| `options` | Available choices (`[{id, label}]`) |
| `selected_option` | The chosen option (set on approval) |
| `evidence` | Supporting data (JSON) |
| `rationale` | Concise reason (no chain-of-thought) |
| `risk_level` | `low` / `medium` / `high` / `critical` |
| `risk` | Risk assessment details (JSON) |
| `budget_impact` | Financial impact (JSON) |
| `required_authority` | Minimum authority level needed to decide |
| `status` | Current lifecycle status |

### Decision Reviews (Audit Trail)

Every `submit`, `approve`, `reject`, and `implement` action is recorded in `decision_reviews`:

| Field | Description |
|-------|-------------|
| `reviewer_id` | Who reviewed |
| `verdict` | `approve` / `reject` / `request_revision` |
| `rationale` | Why |
| `previous_status` | Status before this action |

### Security Boundaries

- Decisions **require authorized review** — they never auto-execute.
- `required_authority` is checked against the reviewer's `authority_level`.
- Recommendations are **never auto-executed**.

### API

- `POST /api/v1/companies/{id}/decisions` — create decision
- `GET /api/v1/companies/{id}/decisions` — list (filter by `status`)
- `GET /api/v1/decisions/{id}` — detail
- `POST /api/v1/decisions/{id}/submit?actor_id=` — submit for review
- `POST /api/v1/decisions/{id}/approve?reviewer_id=` — approve (body: `{rationale}`)
- `POST /api/v1/decisions/{id}/reject?reviewer_id=` — reject (body: `{rationale}`)
- `POST /api/v1/decisions/{id}/implement?actor_id=` — implement approved decision
- `GET /api/v1/decisions/{id}/reviews` — audit trail

---

## Risks

Risks are tracked by severity and status:

| `severity` | `status` transitions |
|-------------|---------------------|
| `low` / `medium` / `high` / `critical` | `open` → `mitigating` → `monitored` → `resolved` / `accepted` |

### API

- `POST /api/v1/companies/{id}/risks` — create risk
- `GET /api/v1/companies/{id}/risks` — list (filter by `severity`)
- `GET /api/v1/risks/{id}` — detail
- `PUT /api/v1/risks/{id}` — update (status, mitigation, etc.)

---

## Alerts

Alerts are generated by **threshold-based rules** in `AlertManager.generate_alerts()`:

| Rule | Trigger | Severity |
|------|---------|----------|
| Budget overrun | `utilization_pct > 80%` | `warning` |
| Budget critical | `utilization_pct > 95%` | `critical` |
| Verification drop | `pass_rate < 85%` | `warning` |
| Goal at-risk | Goal `status = at_risk` | `informational` |

### Lifecycle

```
active → acknowledged → resolved
```

### API

- `GET /api/v1/companies/{id}/alerts` — list (filter by `severity`)
- `POST /api/v1/companies/{id}/alerts/check` — run threshold checks
- `POST /api/v1/alerts/{id}/acknowledge` — acknowledge
- `POST /api/v1/alerts/{id}/resolve` — resolve

---

## Company Health

`CompanyHealth` computes a **composite health score** across 6 dimensions, each with exposed weights:

| Dimension | Weight | Source |
|-----------|--------|--------|
| `execution` | 0.20 | Task success rate, completion rate |
| `quality` | 0.20 | Average verification score |
| `reliability` | 0.20 | Verification pass rate, recovery rate |
| `cost` | 0.15 | Budget utilization efficiency |
| `goal_progress` | 0.15 | Weighted average goal progress |
| `risk_posture` | 0.10 | Open risks by severity |

The `overall_score` (0–100) determines the health `status`:
- **`healthy`** — score ≥ 70
- **`degraded`** — score 40–69
- **`critical`** — score < 40

### Health Snapshot

```json
{
  "company_id": "company-uuid",
  "overall_score": 78,
  "status": "degraded",
  "dimensions": {
    "execution": 85,
    "quality": 80,
    "reliability": 70,
    "cost": 75,
    "goal_progress": 65,
    "risk_posture": 82
  },
  "weights": {
    "execution": 0.2,
    "quality": 0.2,
    "reliability": 0.2,
    "cost": 0.15,
    "goal_progress": 0.15,
    "risk_posture": 0.1
  },
  "computed_at": "2026-03-01T00:00:00Z"
}
```

### API

- `GET /api/v1/companies/{id}/health` — current health score

---

## Reports

Reports are structured summaries of company performance. The `ReportGenerator` collects authoritative metrics and produces a report; `verify()` cross-checks report metrics against source data.

| `report_type` | Description |
|---------------|-------------|
| `weekly` | Weekly operating report |
| `company` | Full company report |
| `health` | Health-focused report |

### Report Structure

```json
{
  "metrics": { "tasks_completed": 42, "success_rate": 0.93 },
  "highlights": ["Goal progress reached 45%"],
  "risks": [{ "title": "Budget overrun", "severity": "high" }],
  "blockers": ["Slow verification pipeline"],
  "goal_progress": { "goal-uuid": 0.45 },
  "recommendations": ["Increase reviewer capacity"],
  "verification_status": "verified",
  "verification_summary": "All metrics cross-checked"
}
```

**Recommendations are non-executing** — they are informational only.

### API

- `GET /api/v1/companies/{id}/reports` — list reports
- `POST /api/v1/companies/{id}/reports/generate?report_type=weekly` — generate report

---

## Analytics

`AnalyticsService` aggregates data across five domains:

| Domain | Metrics |
|--------|---------|
| `workforce` | Employee count, active, by-status, by-department |
| `operations` | Task volume, success rate, avg latency |
| `reliability` | Verification pass rate, recovery rate |
| `finance` | Total cost, budget utilization, cost per task |
| `strategy` | Goal progress, active goals, at-risk goals |

`ForecastService` provides deterministic projections:
- **Budget projection**: `spent / days_elapsed × 30`
- **Goal completion**: extrapolation from current progress rate

### API

- `GET /api/v1/companies/{id}/analytics` — full analytics

---

## Event Timeline

Every significant action is logged to `organizational_events` via `OrgEventLogger`:

```json
{
  "actor": "CEO",
  "action": "decision_approved",
  "target_type": "decision",
  "target_id": "decision-uuid",
  "details": { "approved_option": "Approve migration" },
  "outcome": "success",
  "correlation_id": "optional-grouping-id"
}
```

### API

- `GET /api/v1/companies/{id}/timeline?limit=50` — recent events

---

## Org-Aware Routing

`OrgRoutingService` extends the Phase 7 assignment engine with company-awareness:

1. **Skill matching** — same as Phase 7 (40% weight)
2. **Workload availability** — same as Phase 7 (30% weight)
3. **Role match** — employee's organizational role matches task requirements (20% weight)
4. **Performance** — real success rate from execution history (10% weight)

Additional filters:
- Employee must be `active` in the company
- Employee must have budget remaining
- Employee's department policies must not block the task

Every assignment returns **explainability**: selected employee, candidates evaluated, per-candidate scores, and reasoning.

---

## Delegation

`DelegationService` verifies before delegating work down the hierarchy:

1. **Authority** — delegator has sufficient `authority_level`
2. **Capability** — delegatee has required skills
3. **Permissions** — delegatee has access to required tools
4. **Workload** — delegatee can accept more tasks
5. **Budget** — delegatee has budget remaining
6. **Policy** — delegation doesn't violate any policy

**Self-privilege-granting is prevented** — an employee cannot delegate to themselves or escalate their own authority.

---

## Company Memory

`CompanyMemoryService` delegates to the existing `MemoryService` using namespace conventions:

| Scope | Namespace | Example |
|-------|-----------|---------|
| Company | `company:{name}` | `company:nexus-labs` |
| Department | `department:{id}` | `department:dept-uuid` |

Stores decisions, policies, lessons, and reports as validated structured knowledge.

---

## Security & Scope Boundaries

The Company Layer enforces these non-negotiable boundaries:

1. **No autonomous strategy generation** — strategy is human-defined
2. **No autonomous hiring/firing** — employee lifecycle is managed through the Employee OS
3. **No unlimited budgets** — all spending checked against limits
4. **No self-privilege** — employees cannot grant themselves elevated permissions
5. **No autonomous finance/legal** — financial and legal decisions require human review
6. **Recommendations are non-executing** — reports contain recommendations but never auto-execute them
7. **Decisions require authorized review** — every decision goes through submit → review → approve/reject → implement with full audit trail
8. **KPI values are computed server-side** — never user-submitted, always from authoritative data

---

## Database Migration

Phase 8 adds a single Alembic migration (`0010_company_layer`) with 15 new tables:

`companies`, `departments`, `organizational_memberships`, `organizational_roles`, `goals`, `kpis`, `kpi_values`, `budgets`, `policies`, `decisions`, `decision_reviews`, `risks`, `alerts`, `company_reports`, `organizational_events`

All enums use the `StrEnum` convention (`native_enum=False`) for PostgreSQL/SQLite portability. Scope-discriminated tables (`scope_type` + `scope_id`) avoid duplicating entity types across company/department/employee scope.

---

## Frontend Pages

| Page | Route | Description |
|------|-------|-------------|
| Company List | `/companies` | List all companies with health cards |
| Executive Dashboard | `/companies/[id]` | Health, stats, goals, KPIs, budgets, risks, alerts, timeline |
| Organization Chart | `/companies/[id]/organization-chart` | Recursive tree visualization |
| Goals | `/companies/[id]/goals` | Goal tree with scope filter |
| KPIs | `/companies/[id]/kpis` | KPI dashboard with sparklines |
| Budget | `/companies/[id]/budget` | Company + department budget cards |
| Decisions | `/companies/[id]/decisions` | Decision list with status filter |
| Decision Detail | `/companies/[id]/decisions/[decisionId]` | Full decision with submit/approve/reject/implement |
| Risks | `/companies/[id]/risks` | Risk list sorted by severity |
| Alerts | `/companies/[id]/alerts` | Alert center with run-checks |
| Department Detail | `/companies/[id]/department/[deptId]` | 5 tabs: overview, goals, KPIs, employees, risks |

---

## Testing

18+ dedicated test suites cover:

- Company lifecycle (create/activate/pause/archive, invalid transitions, isolation)
- Department hierarchy, managers, memberships
- Organizational chart construction
- Goal cascade and progress computation
- KPI computation from authoritative sources
- Budget allocation, enforcement, hierarchical limits
- Policy inheritance and most-restrictive-wins resolution
- Decision lifecycle with audit trail
- Risk severity and status transitions
- Alert threshold detection and lifecycle
- Company health scoring across dimensions
- Report generation and verification
- Org-aware routing with explainability
- Delegation authority/capability checks
- Company memory namespace isolation
- Full API route coverage with response models

---

## Demos

Three deterministic, DB-backed demos:

1. **Company Goal Demo** — seed a company goal → cascade to department → route to employees → execute via multi-agent orchestration → verify → recompute KPI → goal progress visible on dashboard.

2. **Weekly Operating Cycle** — Phase 3 workflow that collects KPI metrics → aggregates departments → checks budgets/goals → generates report → verifies → creates alerts if needed → stores report.

3. **Health Degradation Chain** — lower a department's verification rate → run alert checks → verify KPI decline → alert created → risk updated → dashboard shows warning with explainable cause.
