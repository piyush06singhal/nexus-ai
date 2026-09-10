# NEXUS — AI Employee OS (Phase 7)

> **Phase 7: AI Employee OS.** Transforms NEXUS from an agent orchestration platform into an **AI workforce platform** — creating, configuring, managing, assigning, supervising, and evaluating persistent **AI Employees** that wrap existing agents with organizational identity, skills, goals, policies, budgets, and performance tracking.

---

## 1. Architecture Overview

```
API → Application Services → Employee OS → Existing Orchestration/Runtime Systems
```

The Employee OS layer sits **on top of** the existing Agent Runtime, Workflow Engine, Memory, and Orchestration subsystems. It does NOT replace or modify any Phase 1–6 code.

### What Employee OS owns:
- Identity, role, skills, responsibilities
- Goals and progress tracking
- Workload management and capacity
- Policies and budgets
- Performance metrics and reviews
- Templates and instantiation
- Audit logging and timeline

### What Employee OS does NOT own:
- Model execution (Agent Runtime)
- Tool execution (ToolExecutor)
- Memory implementation (Memory System)
- Workflow execution (Workflow Engine)
- Verification implementation (Verification Service)

---

## 2. Data Model

### Tables (migration `0009_ai_employee_os`)

**`ai_employees`** — Core identity table
- `id` (UUID PK), `name` (unique), `display_name`, `description`
- `role` (str 64), `department` (str 64 nullable)
- `status` (EmployeeStatus), `availability` (EmployeeAvailability)
- `agent_id` (FK → agents.id nullable)
- JSON fields: `skills`, `responsibilities`, `goals`, `tools`, `permissions`, `work_preferences`, `workload_config`, `performance_profile`, `policies`
- `memory_namespace` (str 128 nullable) — for Phase 4 memory isolation
- `created_at`, `updated_at`

**`employee_goals`** — Goal tracking
- `id`, `employee_id` (FK), `title`, `description`, `priority`, `target`, `metric`
- `deadline` (datetime nullable), `status` (GoalStatus), `progress` (float 0–1)
- `parent_goal_id` (UUID nullable) — for goal hierarchies

**`employee_budgets`** — Resource tracking
- `id`, `employee_id` (FK unique), `monthly_limit`, `task_limit`
- `tokens_used`, `cost_used`, `tool_calls_used`
- `period_start`, `period_end`

**`employee_reviews`** — Performance reviews
- `id`, `employee_id` (FK), `period_start`, `period_end`
- JSON: `metrics`, `strengths`, `weaknesses`, `skill_changes`, `recommendations`
- `reviewer` (str — "system" or user ID)

**`employee_templates`** — Reusable configs
- `id`, `name` (unique), `description`, `role`
- JSON: `skills`, `responsibilities`, `tools`, `policies`, `verification_policy`

**`employee_audit_log`** — Append-only audit trail
- `id`, `employee_id` (FK nullable), `actor`, `action`, `target_type`, `target_id`
- JSON: `details`, `correlation_id`, `outcome`

---

## 3. Lifecycle State Machine

```
draft → active
active → busy | paused | suspended | terminated
busy → active | suspended | terminated
paused → active | terminated
suspended → active | terminated
on_leave → active | terminated
```

**TERMINATED is final** — no transitions out. A terminated employee cannot receive tasks.

`is_available_for_tasks(status)` returns `True` for `active` and `busy`.

---

## 4. Skills

`SkillAssessor` manages employee skills with adaptive learning:

- **Add/update/remove** skills on an employee
- **Proficiency** (0.0–1.0) increases on successful task use, decreases on failure
- **Learning rate**: `0.1 * (1.0 - proficiency)` — faster growth at low proficiency, slower as mastery increases
- **Confidence** tracks how certain we are in the proficiency estimate (increases with evidence)
- **Evidence count** tracks total observations

---

## 5. Goals

`GoalTracker` manages employee goals:

- Goals transition through: `not_started → active → completed/failed/cancelled`
- Progress updates auto-activate goals (progress > 0) and auto-complete at 1.0
- Priority ordering — higher priority goals surface first
- `overall_progress()` computes average across active goals

---

## 6. Assignment Engine

`AssignmentEngine` selects the best employee for a task:

**Scoring (weighted):**
- 40% Skill match — `SkillAssessor.match_skills()` scores required skills vs employee skills
- 30% Workload availability — available slots / capacity
- 20% Role match — preferred role matches employee role
- 10% Performance — real `PerformanceTracker` success rate

**Assignment persists real work:** every successful assignment creates a real
`Task` (owned by the employee's backing agent, status `queued`) via
`TaskService`, and the returned `AssignmentResult` carries the new `task_id`.
The assigned task is then executable through the standard runtime and its
outcome feeds the employee's performance profile.

**Two modes:**
- `assign(request)` — auto-selects the best employee from all eligible candidates
- `assign_specific(employee_id, request)` — targets a specific employee (still checks availability and workload)

Both return an `AssignmentResult` with success, employee info, score, reasoning, and candidates evaluated.

---

## 7. Workload Management

`WorkloadManager` tracks real, persisted workload:

- **Task counts** derived from real `Task` rows owned by the employee's backing
  agent (`tasks WHERE assigned_agent_id = employee.agent_id`), grouped by
  status — queued / in-progress / completed / failed
- **Capacity** parsed from `workload_config` JSON (default: `employee_default_capacity` setting)
- **Available slots** = capacity − active tasks
- **Utilization** = active tasks / capacity (capped at 1.0)
- `can_accept_task()` checks status + available capacity
- `get_available_employees()` returns IDs of ACTIVE/BUSY employees with AVAILABLE/BUSY availability

A `GET /employees/{id}/workload` snapshot reflects the employee's assigned
tasks, so assigning then executing a task moves its counts from queued to
completed for real.

---

## 8. Performance Tracking

`PerformanceTracker` maintains running averages:

- Task completions, failures, success rate
- Verification pass rate, recovery rate
- Average quality, latency, cost, tokens
- Utilization, deadline adherence

`PerformanceReviewer` generates reviews:
- High performance (>80% success): strengths + skill-based recommendations
- Low performance (<80%): weaknesses + improvement recommendations

---

## 9. Context Builder

`EmployeeContextBuilder` builds execution context for an employee:

**Context sections (priority-ordered):**
1. Identity — name, role, department, status
2. Responsibilities — current responsibilities
3. Goals — active goals with progress
4. Skills — proficiency levels
5. Tools — available tools
6. Policies — verification and behavior policies
7. Current task — task description when executing

**Token budget**: truncation by priority (later sections truncated first), estimated at 4 tokens per character.

---

## 10. Templates

`TemplateService` manages reusable employee configurations:

- CRUD for templates
- `create_from_template(template_id, overrides)`:
  - Clones: role, skills, responsibilities, tools, permissions, policies
  - Does NOT clone: memories, credentials, active tasks, history
  - Supports overrides: role, description, skills, responsibilities, tools, policies

---

## 11. Memory Integration

Employee memory uses the existing Phase 4 Memory System:

- Each employee has a `memory_namespace` (default: `employee:{name}`)
- Memory stored in the existing `memories` table, scoped by namespace
- Access control: employee A cannot access employee B's private namespace
- `EmployeeContextBuilder` queries memories via the existing `MemoryManager`

---

## 12. Workflow Integration

`WorkflowStepType.EMPLOYEE_TASK` — a new step type:

1. Resolves employee by ID
2. Builds employee context via `EmployeeContextBuilder`
3. Resolves the employee's underlying agent
4. Creates a task in the Agent Runtime
5. Executes via the existing `AgentRuntime`
6. Returns employee_id, employee_name, employee_context, and output

Step configuration:
```json
{
  "employee_id": "uuid",
  "task_title": "Analyze data",
  "task_description": "Perform Q1 analysis",
  "input_mapping": {}
}
```

---

## 13. Audit & Timeline

`AuditLogger` records every significant operation:

- Created, activated, paused, resumed, suspended, terminated
- Goal created, skill added, task assigned
- Budget exceeded, permission denied
- Each entry: actor, employee, action, target, timestamp, correlation_id, outcome

**Respects `employee_audit_enabled`** setting — when disabled, returns transient objects without DB writes.

Timeline is derived from the audit log, providing a chronological view of employee activity.

---

## 14. API Endpoints

### Employees (`/api/v1/employees`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/employees` | Create employee |
| GET | `/employees` | List employees (filters: status, role) |
| GET | `/employees/{id}` | Get employee |
| PUT | `/employees/{id}` | Update employee |
| DELETE | `/employees/{id}` | Delete employee |
| POST | `/employees/{id}/activate` | Activate |
| POST | `/employees/{id}/pause` | Pause |
| POST | `/employees/{id}/resume` | Resume |
| POST | `/employees/{id}/suspend` | Suspend |
| POST | `/employees/{id}/terminate` | Terminate |
| POST | `/employees/{id}/tasks` | Assign task |
| POST | `/employees/assign` | Auto-assign task |
| GET | `/employees/{id}/workload` | Workload snapshot |
| GET | `/employees/{id}/skills` | Skills |
| GET | `/employees/{id}/goals` | Goals |
| POST | `/employees/{id}/goals` | Create goal |
| GET | `/employees/{id}/performance` | Performance metrics |
| GET | `/employees/{id}/reviews` | Reviews |
| GET | `/employees/{id}/timeline` | Activity timeline |
| GET | `/employees/{id}/audit` | Audit log |
| GET | `/employees/workforce` | Workforce overview |

### Templates (`/api/v1/employee-templates`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/employee-templates` | List templates |
| POST | `/employee-templates` | Create template |
| GET | `/employee-templates/{id}` | Get template |
| POST | `/employee-templates/{id}/create` | Create employee from template |

---

## 15. Configuration

```python
# AI Employee OS (Phase 7)
employee_default_capacity: int = 5          # Default max concurrent tasks per employee
employee_max_concurrent_tasks: int = 5      # System-wide max concurrent tasks
employee_budget_default_monthly: float = 50.0  # Default monthly budget ($)
employee_evaluation_on_task_complete: bool = False  # Auto-evaluate on task completion
employee_context_max_tokens: int = 4000     # Max tokens in employee context
employee_audit_enabled: bool = True         # Enable/disable audit logging
```

---

## 16. Frontend Pages

| Page | Description |
|------|-------------|
| `/employees` | Employee Directory — list, filter, create, templates |
| `/employees/[id]` | Employee Detail — identity, skills, goals, performance, timeline, audit |
| `/employee-workbench` | Workbench — status-grouped view of all employees |
| `/employee-goals` | Goals Dashboard — goals across employees with progress bars |
| `/employee-performance` | Performance Dashboard — aggregate and per-employee metrics |

---

## 17. Tests

71 backend tests across 9 test files:

| File | Tests | Coverage |
|------|-------|----------|
| `test_employee_lifecycle.py` | 12 | State machine, transitions, CRUD, budget creation |
| `test_employee_skills.py` | 9 | Add/update/remove, proficiency, matching |
| `test_employee_goals.py` | 8 | Create, progress, completion, cancel, filtering |
| `test_employee_assignment.py` | 8 | Auto-assign, specific, skill matching, explainability |
| `test_employee_workload.py` | 6 | Snapshot, capacity, config, available employees |
| `test_employee_templates.py` | 6 | CRUD, create from template, overrides |
| `test_employee_performance.py` | 6 | Metrics, reviews, verification pass rate |
| `test_employee_audit.py` | 8 | Audit events, timeline, log limits |
| `test_employee_context.py` | 9 | Context sections, truncation, nonexistent employee |

16 frontend type tests in `types-phase7.test.ts`.
