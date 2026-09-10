"""AI Employee OS endpoints (Phase 7)."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.models.employee import EmployeeStatus
from app.db.models.execution import AgentExecution
from app.db.session import get_db
from app.employee.lifecycle import EmployeeLifecycleError
from app.employee.manager import EmployeeManager
from app.employee.types import AssignmentRequest
from app.runtime.runtime import AgentRuntime
from app.schemas.employee import (
    AssignmentRequestSchema,
    AssignmentResultSchema,
    AuditEntry,
    EmployeeCreate,
    EmployeeList,
    EmployeeRead,
    EmployeeUpdate,
    GoalCreate,
    GoalRead,
    PerformanceRead,
    ReviewRead,
    TimelineEvent,
    WorkforceOverview,
    WorkloadRead,
)
from app.schemas.execution import ExecutionRead
from app.schemas.task import TaskRead
from app.services.dependencies import create_runtime
from app.services.execution_service import to_dict as execution_to_dict

router = APIRouter(tags=["employees"], prefix="/employees")


def _emp_to_read(emp) -> EmployeeRead:
    """Convert an AIEmployee ORM object to EmployeeRead schema."""
    return EmployeeRead(
        id=emp.id,
        name=emp.name,
        display_name=emp.display_name,
        description=emp.description,
        role=emp.role,
        department=emp.department,
        status=emp.status,
        availability=emp.availability,
        agent_id=emp.agent_id,
        skills=json.loads(emp.skills) if emp.skills else None,
        responsibilities=json.loads(emp.responsibilities) if emp.responsibilities else None,
        goals=json.loads(emp.goals) if emp.goals else None,
        tools=json.loads(emp.tools) if emp.tools else None,
        permissions=json.loads(emp.permissions) if emp.permissions else None,
        memory_namespace=emp.memory_namespace,
        work_preferences=json.loads(emp.work_preferences) if emp.work_preferences else None,
        workload_config=json.loads(emp.workload_config) if emp.workload_config else None,
        performance_profile=(
            json.loads(emp.performance_profile) if emp.performance_profile else None
        ),
        policies=json.loads(emp.policies) if emp.policies else None,
        created_at=emp.created_at,
        updated_at=emp.updated_at,
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an AI employee",
)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeRead:
    mgr = EmployeeManager(db)
    emp = mgr.create(
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        role=payload.role,
        department=payload.department,
        agent_id=payload.agent_id,
        skills=payload.skills,
        responsibilities=payload.responsibilities,
        tools=payload.tools,
        permissions=payload.permissions,
        policies=payload.policies,
        workload_config=payload.workload_config,
    )
    return _emp_to_read(emp)


@router.get(
    "",
    response_model=EmployeeList,
    summary="List AI employees",
)
def list_employees(
    emp_status: EmployeeStatus | None = Query(default=None, alias="status"),  # noqa: B008
    role: str | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeList:
    mgr = EmployeeManager(db)
    emps = mgr.list_(status=emp_status, role=role)
    return EmployeeList(
        items=[_emp_to_read(e) for e in emps],
        total=len(emps),
    )


@router.get(
    "/workforce",
    response_model=WorkforceOverview,
    summary="Workforce overview stats",
)
def workforce_overview(
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkforceOverview:
    mgr = EmployeeManager(db)
    return WorkforceOverview(**mgr.workforce_overview())


@router.get(
    "/{employee_id}",
    response_model=EmployeeRead,
    summary="Get an AI employee",
)
def get_employee(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeRead:
    mgr = EmployeeManager(db)
    emp = mgr.get(employee_id)
    if emp is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Employee not found")
    return _emp_to_read(emp)


@router.put(
    "/{employee_id}",
    response_model=EmployeeRead,
    summary="Update an AI employee",
)
def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeRead:
    mgr = EmployeeManager(db)
    fields = payload.model_dump(exclude_unset=True)
    emp = mgr.update(employee_id, **fields)
    if emp is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Employee not found")
    return _emp_to_read(emp)


@router.delete(
    "/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an AI employee",
)
def delete_employee(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    mgr = EmployeeManager(db)
    deleted = mgr.delete(employee_id)
    if not deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Employee not found")


# ── Lifecycle ─────────────────────────────────────────────────────────────────


@router.post(
    "/{employee_id}/activate",
    response_model=EmployeeRead,
    summary="Activate an employee",
)
def activate_employee(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeRead:
    mgr = EmployeeManager(db)
    try:
        emp = mgr.activate(employee_id)
    except EmployeeLifecycleError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=str(e)) from e
    return _emp_to_read(emp)


@router.post(
    "/{employee_id}/pause",
    response_model=EmployeeRead,
    summary="Pause an employee",
)
def pause_employee(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeRead:
    mgr = EmployeeManager(db)
    try:
        emp = mgr.pause(employee_id)
    except EmployeeLifecycleError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=str(e)) from e
    return _emp_to_read(emp)


@router.post(
    "/{employee_id}/resume",
    response_model=EmployeeRead,
    summary="Resume a paused employee",
)
def resume_employee(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeRead:
    mgr = EmployeeManager(db)
    try:
        emp = mgr.resume(employee_id)
    except EmployeeLifecycleError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=str(e)) from e
    return _emp_to_read(emp)


@router.post(
    "/{employee_id}/suspend",
    response_model=EmployeeRead,
    summary="Suspend an employee",
)
def suspend_employee(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeRead:
    mgr = EmployeeManager(db)
    try:
        emp = mgr.suspend(employee_id)
    except EmployeeLifecycleError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=str(e)) from e
    return _emp_to_read(emp)


@router.post(
    "/{employee_id}/terminate",
    response_model=EmployeeRead,
    summary="Terminate an employee",
)
def terminate_employee(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmployeeRead:
    mgr = EmployeeManager(db)
    try:
        emp = mgr.terminate(employee_id)
    except EmployeeLifecycleError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=str(e)) from e
    return _emp_to_read(emp)


# ── Assignment ────────────────────────────────────────────────────────────────


@router.post(
    "/{employee_id}/tasks",
    response_model=AssignmentResultSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a task to an employee",
)
def assign_task(
    employee_id: UUID,
    payload: AssignmentRequestSchema,
    db: Session = Depends(get_db),  # noqa: B008
) -> AssignmentResultSchema:
    mgr = EmployeeManager(db)
    req = AssignmentRequest(
        task_id=payload.task_id,
        task_title=payload.task_title,
        task_description=payload.task_description,
        required_skills=payload.required_skills,
        preferred_role=payload.preferred_role,
        priority=payload.priority,
    )
    result = mgr.assign_task_to(employee_id, req)
    return AssignmentResultSchema(
        success=result.success,
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        task_id=result.task_id,
        score=result.score,
        reasoning=result.reasoning,
        candidates_evaluated=result.candidates_evaluated,
    )


@router.post(
    "/assign",
    response_model=AssignmentResultSchema,
    summary="Auto-assign a task to the best employee",
)
def auto_assign_task(
    payload: AssignmentRequestSchema,
    db: Session = Depends(get_db),  # noqa: B008
) -> AssignmentResultSchema:
    mgr = EmployeeManager(db)
    req = AssignmentRequest(
        task_id=payload.task_id,
        task_title=payload.task_title,
        task_description=payload.task_description,
        required_skills=payload.required_skills,
        preferred_role=payload.preferred_role,
        priority=payload.priority,
    )
    result = mgr.assign_task(req)
    return AssignmentResultSchema(
        success=result.success,
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        task_id=result.task_id,
        score=result.score,
        reasoning=result.reasoning,
        candidates_evaluated=result.candidates_evaluated,
    )


@router.get(
    "/{employee_id}/tasks",
    response_model=list[TaskRead],
    summary="List an employee's tasks (task inbox)",
)
def list_employee_tasks(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[TaskRead]:
    mgr = EmployeeManager(db)
    tasks = mgr.get_tasks(employee_id)
    return [TaskRead.model_validate(t) for t in tasks]


@router.post(
    "/{employee_id}/tasks/{task_id}/execute",
    response_model=ExecutionRead,
    summary="Execute an employee's task and record performance",
)
def execute_employee_task(
    employee_id: UUID,
    task_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
    runtime: AgentRuntime = Depends(create_runtime),  # noqa: B008
) -> ExecutionRead:
    mgr = EmployeeManager(db)
    execution: AgentExecution = mgr.run_employee_task(employee_id, task_id, runtime)
    return ExecutionRead.model_validate(execution_to_dict(execution))


# ── Workload / Skills / Goals / Performance ───────────────────────────────────


@router.get(
    "/{employee_id}/workload",
    response_model=WorkloadRead,
    summary="Get employee workload",
)
def get_workload(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> WorkloadRead:
    mgr = EmployeeManager(db)
    snap = mgr.get_workload(employee_id)
    return WorkloadRead(
        employee_id=snap.employee_id,
        active_tasks=snap.active_tasks,
        queued_tasks=snap.queued_tasks,
        completed_tasks=snap.completed_tasks,
        failed_tasks=snap.failed_tasks,
        capacity=snap.capacity,
        utilization=snap.utilization,
        available_slots=snap.available_slots,
    )


@router.get(
    "/{employee_id}/skills",
    summary="Get employee skills",
)
def get_skills(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    mgr = EmployeeManager(db)
    skills = mgr.get_skills(employee_id)
    return [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "category": s.category,
            "proficiency": s.proficiency,
            "confidence": s.confidence,
            "evidence_count": s.evidence_count,
        }
        for s in skills
    ]


@router.get(
    "/{employee_id}/goals",
    response_model=list[GoalRead],
    summary="Get employee goals",
)
def get_goals(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[GoalRead]:
    mgr = EmployeeManager(db)
    goals = mgr.get_goals(employee_id)
    return [GoalRead.model_validate(g) for g in goals]


@router.post(
    "/{employee_id}/goals",
    response_model=GoalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a goal for an employee",
)
def create_goal(
    employee_id: UUID,
    payload: GoalCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> GoalRead:
    mgr = EmployeeManager(db)
    goal = mgr.create_goal(
        employee_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        target=payload.target,
        metric=payload.metric,
    )
    return GoalRead.model_validate(goal)


@router.get(
    "/{employee_id}/performance",
    response_model=PerformanceRead,
    summary="Get employee performance metrics",
)
def get_performance(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> PerformanceRead:
    mgr = EmployeeManager(db)
    metrics = mgr.get_performance(employee_id)
    return PerformanceRead(
        employee_id=metrics.employee_id,
        tasks_completed=metrics.tasks_completed,
        tasks_failed=metrics.tasks_failed,
        success_rate=metrics.success_rate,
        verification_pass_rate=metrics.verification_pass_rate,
        average_quality=metrics.average_quality,
        recovery_rate=metrics.recovery_rate,
        average_latency_ms=metrics.average_latency_ms,
        total_cost=metrics.total_cost,
        total_tokens=metrics.total_tokens,
        utilization=metrics.utilization,
        deadline_adherence=metrics.deadline_adherence,
        period_start=metrics.period_start,
        period_end=metrics.period_end,
    )


@router.get(
    "/{employee_id}/reviews",
    response_model=list[ReviewRead],
    summary="Get employee reviews",
)
def get_reviews(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ReviewRead]:
    mgr = EmployeeManager(db)
    reviews = mgr.get_reviews(employee_id)
    return [ReviewRead.model_validate(r) for r in reviews]


# ── Timeline / Audit ──────────────────────────────────────────────────────────


@router.get(
    "/{employee_id}/timeline",
    response_model=list[TimelineEvent],
    summary="Get employee activity timeline",
)
def get_timeline(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[TimelineEvent]:
    mgr = EmployeeManager(db)
    events = mgr.get_timeline(employee_id)
    return [TimelineEvent(**e) for e in events]


@router.get(
    "/{employee_id}/audit",
    response_model=list[AuditEntry],
    summary="Get employee audit log",
)
def get_audit(
    employee_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[AuditEntry]:
    mgr = EmployeeManager(db)
    entries = mgr.get_audit_log(employee_id)
    return [AuditEntry(**e) for e in entries]
