"""AI Employee OS — central manager service.

``EmployeeManager(db)`` provides CRUD, lifecycle operations, task assignment,
workload queries, template instantiation, and context building.  Business
logic stays here, not in routes.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.agent import Agent, AgentStatus
from app.db.models.employee import (
    AIEmployee,
    EmployeeAvailability,
    EmployeeBudget,
    EmployeeGoal,
    EmployeeReview,
    EmployeeStatus,
)
from app.db.models.execution import AgentExecution
from app.db.models.task import Task
from app.employee.assignment import AssignmentEngine
from app.employee.audit import AuditLogger
from app.employee.context import EmployeeContextBuilder
from app.employee.goals import GoalTracker
from app.employee.lifecycle import validate_transition
from app.employee.performance import PerformanceReviewer, PerformanceTracker
from app.employee.skills import SkillAssessor
from app.employee.templates import TemplateService
from app.employee.types import (
    AssignmentRequest,
    AssignmentResult,
    PerformanceMetrics,
    SkillEntry,
    WorkloadSnapshot,
)
from app.employee.workload import WorkloadManager
from app.runtime.runtime import AgentRuntime
from app.schemas.task import TaskCreate
from app.services.task_service import TaskService
from app.services.task_service import to_dict as task_to_dict


class EmployeeManager:
    """Central service for AI Employee operations."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.audit = AuditLogger(db)
        self.skills = SkillAssessor(db)
        self.goals = GoalTracker(db)
        self.workload = WorkloadManager(db)
        self.assignment = AssignmentEngine(db)
        self.context = EmployeeContextBuilder(db)
        self.performance = PerformanceTracker(db)
        self.reviewer = PerformanceReviewer(db)
        self.templates = TemplateService(db)

    # ── CRUD ───────────────────────────────────────────────────────────

    def create(
        self,
        *,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        role: str = "general",
        department: str | None = None,
        agent_id: UUID | None = None,
        skills: list[dict[str, Any]] | None = None,
        responsibilities: list[str] | None = None,
        tools: list[str] | None = None,
        permissions: list[str] | None = None,
        policies: dict[str, Any] | None = None,
        workload_config: dict[str, Any] | None = None,
    ) -> AIEmployee:
        """Create a new AI employee.

        When *agent_id* is ``None``, a backing :class:`Agent` is auto-created
        (mock provider, active status) so the employee can own real tasks.
        """
        # Auto-create a backing agent when none is supplied.
        if agent_id is None:
            agent = self._create_backing_agent(name, role)
            agent_id = agent.id

        employee = AIEmployee(
            name=name,
            display_name=display_name or name,
            description=description,
            role=role,
            department=department,
            status=EmployeeStatus.DRAFT,
            availability=EmployeeAvailability.UNAVAILABLE,
            agent_id=agent_id,
            skills=json.dumps(skills) if skills else None,
            responsibilities=json.dumps(responsibilities) if responsibilities else None,
            tools=json.dumps(tools) if tools else None,
            permissions=json.dumps(permissions) if permissions else None,
            policies=json.dumps(policies) if policies else None,
            workload_config=json.dumps(workload_config) if workload_config else None,
            memory_namespace=f"employee:{name}",
        )
        self._db.add(employee)
        self._db.flush()

        # Create default budget
        budget = EmployeeBudget(
            employee_id=employee.id,
            monthly_limit=settings.employee_budget_default_monthly,
        )
        self._db.add(budget)
        self._db.flush()

        self.audit.log(
            actor="system",
            action="created",
            employee_id=employee.id,
            target_type="employee",
            target_id=employee.id,
            details={"name": name, "role": role},
            outcome="success",
        )
        self._db.commit()
        return employee

    def get(self, employee_id: UUID) -> AIEmployee | None:
        """Fetch an employee by ID."""
        return self._db.get(AIEmployee, employee_id)

    def list_(
        self,
        *,
        status: EmployeeStatus | None = None,
        role: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AIEmployee]:
        """List employees with optional filters."""
        stmt = select(AIEmployee).order_by(AIEmployee.name)
        if status is not None:
            stmt = stmt.where(AIEmployee.status == status)
        if role is not None:
            stmt = stmt.where(AIEmployee.role == role)
        stmt = stmt.limit(limit).offset(offset)
        return list(self._db.execute(stmt).scalars().all())

    def update(self, employee_id: UUID, **fields: Any) -> AIEmployee | None:
        """Update employee fields (partial update)."""
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return None
        for key, value in fields.items():
            if hasattr(emp, key) and value is not None:
                _json_keys = (
                    "skills",
                    "responsibilities",
                    "tools",
                    "permissions",
                    "policies",
                    "workload_config",
                    "work_preferences",
                    "performance_profile",
                )
                if key in _json_keys and isinstance(value, (list, dict)):
                    setattr(emp, key, json.dumps(value))
                else:
                    setattr(emp, key, value)
        self._db.commit()
        return emp

    def delete(self, employee_id: UUID) -> bool:
        """Delete an employee and cascade."""
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return False
        self.audit.log(
            actor="system",
            action="deleted",
            employee_id=emp.id,
            target_type="employee",
            target_id=emp.id,
            outcome="success",
        )
        self._db.delete(emp)
        self._db.commit()
        return True

    # ── Lifecycle ──────────────────────────────────────────────────────

    def activate(self, employee_id: UUID) -> AIEmployee:
        """Activate an employee (draft → active)."""
        emp = self._require(employee_id)
        validate_transition(emp.status, EmployeeStatus.ACTIVE)
        emp.status = EmployeeStatus.ACTIVE
        emp.availability = EmployeeAvailability.AVAILABLE
        self._db.flush()
        self.audit.log(
            actor="system",
            action="activated",
            employee_id=emp.id,
            target_type="employee",
            target_id=emp.id,
            outcome="success",
        )
        self._db.commit()
        return emp

    def pause(self, employee_id: UUID) -> AIEmployee:
        """Pause an employee."""
        emp = self._require(employee_id)
        validate_transition(emp.status, EmployeeStatus.PAUSED)
        emp.status = EmployeeStatus.PAUSED
        emp.availability = EmployeeAvailability.PAUSED
        self._db.flush()
        self.audit.log(
            actor="system",
            action="paused",
            employee_id=emp.id,
            target_type="employee",
            target_id=emp.id,
            outcome="success",
        )
        self._db.commit()
        return emp

    def resume(self, employee_id: UUID) -> AIEmployee:
        """Resume a paused employee."""
        emp = self._require(employee_id)
        validate_transition(emp.status, EmployeeStatus.ACTIVE)
        emp.status = EmployeeStatus.ACTIVE
        emp.availability = EmployeeAvailability.AVAILABLE
        self._db.flush()
        self.audit.log(
            actor="system",
            action="resumed",
            employee_id=emp.id,
            target_type="employee",
            target_id=emp.id,
            outcome="success",
        )
        self._db.commit()
        return emp

    def suspend(self, employee_id: UUID) -> AIEmployee:
        """Suspend an employee."""
        emp = self._require(employee_id)
        validate_transition(emp.status, EmployeeStatus.SUSPENDED)
        emp.status = EmployeeStatus.SUSPENDED
        emp.availability = EmployeeAvailability.SUSPENDED
        self._db.flush()
        self.audit.log(
            actor="system",
            action="suspended",
            employee_id=emp.id,
            target_type="employee",
            target_id=emp.id,
            outcome="success",
        )
        self._db.commit()
        return emp

    def terminate(self, employee_id: UUID) -> AIEmployee:
        """Terminate an employee."""
        emp = self._require(employee_id)
        validate_transition(emp.status, EmployeeStatus.TERMINATED)
        emp.status = EmployeeStatus.TERMINATED
        emp.availability = EmployeeAvailability.TERMINATED
        self._db.flush()
        self.audit.log(
            actor="system",
            action="terminated",
            employee_id=emp.id,
            target_type="employee",
            target_id=emp.id,
            outcome="success",
        )
        self._db.commit()
        return emp

    # ── Task assignment ────────────────────────────────────────────────

    def assign_task(self, request: AssignmentRequest) -> AssignmentResult:
        """Auto-assign the best employee for a task and persist a real ``Task``."""
        result = self.assignment.assign(request)
        if result.success and result.employee_id:
            return self._persist_assignment(result, request)
        return result

    def assign_task_to(self, employee_id: UUID, request: AssignmentRequest) -> AssignmentResult:
        """Assign a task to a specific employee and persist a real ``Task``."""
        result = self.assignment.assign_specific(employee_id, request)
        if result.success:
            return self._persist_assignment(result, request)
        return result

    def _ensure_backing_agent(self, emp: AIEmployee) -> UUID:
        """Lazily create a backing agent if the employee lacks one."""
        if emp.agent_id is not None:
            return emp.agent_id
        agent = self._create_backing_agent(emp.name, emp.role)
        emp.agent_id = agent.id
        self._db.flush()
        return agent.id

    def _create_backing_agent(self, name: str, role: str) -> Agent:
        """Create an active mock agent that backs an employee.

        Adds and flushes the agent so it carries a real id before the employee
        references it.
        """
        agent = Agent(
            name=f"{name}-agent",
            role=role or "general",
            status=AgentStatus.ACTIVE,
            provider="mock",
            model_name="mock-model",
            description=f"Backing agent for AI employee '{name}'",
            model_params=json.dumps({"reply": '{"summary":"ok","output":{"status":"done"}}'}),
        )
        self._db.add(agent)
        self._db.flush()
        return agent

    def _persist_assignment(
        self, result: AssignmentResult, request: AssignmentRequest
    ) -> AssignmentResult:
        """Persist a real ``Task`` for a successful assignment.

        Ensures the employee has a backing agent, creates a ``Task`` owned by
        that agent via ``TaskService`` (``status=QUEUED``), and returns the
        assignment result carrying the new task's id.
        """
        emp = self._db.get(AIEmployee, result.employee_id)
        if emp is None:
            result.success = False
            result.reasoning = "Employee disappeared during assignment"
            return result
        agent_id = self._ensure_backing_agent(emp)

        task_service = TaskService(self._db)
        task = task_service.create(
            TaskCreate(
                title=request.task_title or "Employee task",
                description=request.task_description or None,
                input_data=request.input_data or None,
            )
        )
        # Move the created task to QUEUED and assign it to the backing agent.
        task = task_service.assign(task.id, agent_id)
        result.task_id = task.id

        self.audit.log(
            actor="system",
            action="task_assigned",
            employee_id=result.employee_id,
            target_type="task",
            target_id=task.id,
            details={
                "task_title": task.title,
                "score": result.score,
            },
            correlation_id=request.correlation_id,
            outcome="success",
        )
        self._db.flush()
        return result

    def get_tasks(self, employee_id: UUID, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return the real tasks owned by an employee's backing agent.

        This is the task inbox backing ``GET /employees/{id}/tasks``.
        """
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None or emp.agent_id is None:
            return []
        stmt = (
            select(Task)
            .where(Task.assigned_agent_id == emp.agent_id)
            .order_by(Task.created_at.desc())
            .limit(limit)
        )
        return [task_to_dict(t) for t in self._db.execute(stmt).scalars().all()]

    def get_task(self, employee_id: UUID, task_id: UUID) -> dict[str, Any] | None:
        """Return a single task if it belongs to the employee's backing agent."""
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None or emp.agent_id is None:
            return None
        task = self._db.get(Task, task_id)
        if task is None or task.assigned_agent_id != emp.agent_id:
            return None
        return task_to_dict(task)

    def run_employee_task(
        self, employee_id: UUID, task_id: UUID, runtime: AgentRuntime
    ) -> AgentExecution:
        """Execute a task on behalf of an employee and record its performance.

        Runs the task through the existing :class:`AgentRuntime` (so the
        execution, tool calls, memories, and cost pipeline all apply), then
        records the outcome into the employee's performance profile — closing
        the real work → metrics loop.
        """
        task = self.get_task(employee_id, task_id)
        if task is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(f"Task {task_id} not found for employee {employee_id}")

        execution = runtime.execute_task(task_id)
        self.performance.record_task_completion(
            employee_id,
            success=execution.status.value == "succeeded",
            latency_ms=execution.latency_ms or 0.0,
            cost=execution.estimated_cost or 0.0,
            tokens=execution.total_tokens or 0,
        )
        self._db.commit()
        return execution

    # ── Skills ─────────────────────────────────────────────────────────

    def get_skills(self, employee_id: UUID) -> list[SkillEntry]:
        """Get employee skills."""
        return self.skills.get_skills(employee_id)

    def add_skill(self, employee_id: UUID, skill: SkillEntry) -> None:
        """Add a skill to an employee."""
        self.skills.add_skill(employee_id, skill)
        self.audit.log(
            actor="system",
            action="skill_added",
            employee_id=employee_id,
            target_type="skill",
            details={"skill_name": skill.name, "skill_id": skill.skill_id},
            outcome="success",
        )
        self._db.commit()

    # ── Goals ──────────────────────────────────────────────────────────

    def get_goals(self, employee_id: UUID) -> list[EmployeeGoal]:
        """Get employee goals."""
        return self.goals.get_goals(employee_id)

    def create_goal(
        self,
        employee_id: UUID,
        *,
        title: str,
        description: str | None = None,
        priority: int = 0,
        target: str | None = None,
        metric: str | None = None,
    ) -> EmployeeGoal:
        """Create a goal for an employee."""
        goal = self.goals.create_goal(
            employee_id,
            title=title,
            description=description,
            priority=priority,
            target=target,
            metric=metric,
        )
        self.audit.log(
            actor="system",
            action="goal_created",
            employee_id=employee_id,
            target_type="goal",
            target_id=goal.id,
            details={"title": title},
            outcome="success",
        )
        self._db.commit()
        return goal

    # ── Workload ───────────────────────────────────────────────────────

    def get_workload(self, employee_id: UUID) -> WorkloadSnapshot:
        """Get employee workload snapshot."""
        return self.workload.get_snapshot(employee_id)

    # ── Performance ────────────────────────────────────────────────────

    def get_performance(self, employee_id: UUID) -> PerformanceMetrics:
        """Get employee performance metrics."""
        return self.performance.get_metrics(employee_id)

    def get_reviews(self, employee_id: UUID) -> list[EmployeeReview]:
        """Get employee reviews."""
        return self.reviewer.get_reviews(employee_id)

    # ── Context ────────────────────────────────────────────────────────

    def build_context(
        self,
        employee_id: UUID,
        *,
        task_description: str = "",
    ) -> dict[str, Any]:
        """Build execution context for an employee."""
        return self.context.build_context(employee_id, task_description=task_description)

    # ── Timeline ───────────────────────────────────────────────────────

    def get_timeline(self, employee_id: UUID, *, limit: int = 50) -> list[dict[str, Any]]:
        """Get employee activity timeline from audit log."""
        entries = self.audit.query(employee_id=employee_id, limit=limit)
        return [
            {
                "event_id": str(e.id),
                "employee_id": str(e.employee_id) if e.employee_id else None,
                "event_type": e.action,
                "description": f"{e.action} by {e.actor}",
                "timestamp": e.created_at.isoformat() if e.created_at else None,
                "outcome": e.outcome,
            }
            for e in entries
        ]

    # ── Audit ──────────────────────────────────────────────────────────

    def get_audit_log(self, employee_id: UUID, *, limit: int = 50) -> list[dict[str, Any]]:
        """Get employee audit log."""
        entries = self.audit.query(employee_id=employee_id, limit=limit)
        return [
            {
                "id": str(e.id),
                "actor": e.actor,
                "action": e.action,
                "target_type": e.target_type,
                "target_id": str(e.target_id) if e.target_id else None,
                "details": json.loads(e.details) if e.details else None,
                "outcome": e.outcome,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]

    # ── Workforce overview ─────────────────────────────────────────────

    def workforce_overview(self) -> dict[str, Any]:
        """Aggregate workforce statistics."""
        stmt = select(AIEmployee)
        all_emps = list(self._db.execute(stmt).scalars().all())
        total = len(all_emps)
        by_status: dict[str, int] = {}
        for e in all_emps:
            s = e.status.value
            by_status[s] = by_status.get(s, 0) + 1
        active = by_status.get("active", 0) + by_status.get("busy", 0)
        return {
            "total_employees": total,
            "active_employees": active,
            "by_status": by_status,
        }

    # ── Helpers ────────────────────────────────────────────────────────

    def _require(self, employee_id: UUID) -> AIEmployee:
        """Fetch an employee or raise ValueError."""
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            raise ValueError(f"Employee {employee_id} not found")
        return emp
