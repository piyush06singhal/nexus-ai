"""Execution — plan coordinated work, then run it through the existing engines.

:class:`ExecutionPlanner` assembles an ``execution_plans`` row that *references*
Phase 1–8 entities (goals, projects, employees, workflows, orchestrations,
tasks) plus verification policy, approval gates, and resource limits — the plan
never re-implements execution. :class:`Executor` runs tasks via the existing
``TaskService`` + ``AgentRuntime.execute_task``, then verifies through
``VerificationService`` and recovers failures through ``RecoveryService``. Every
execution outcome is recorded on the mission graph (execution → task → goal).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.startup import (
    ExecutionPlan,
    ExecutionPlanStatus,
    MissionGraphRelation,
)
from app.services.dependencies import create_runtime
from app.services.recovery_service import RecoveryService
from app.services.verification_service import VerificationService
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.graph import MissionGraphBuilder


class ExecutionPlanner:
    """Assemble and manage an execution plan over existing entities."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    def create(
        self,
        *,
        company_id: UUID,
        mission_id: UUID,
        objective_scope: dict[str, Any],
        startup_plan_id: UUID | None = None,
        project_ids: list[UUID] | None = None,
        employee_ids: list[UUID] | None = None,
        task_ids: list[UUID] | None = None,
        workflow_ids: list[UUID] | None = None,
        orchestration_ids: list[UUID] | None = None,
        verification_policy: dict[str, Any] | None = None,
        resource_limits: dict[str, Any] | None = None,
        status: ExecutionPlanStatus = ExecutionPlanStatus.READY,
    ) -> ExecutionPlan:
        plan = ExecutionPlan(
            mission_id=mission_id,
            startup_plan_id=startup_plan_id,
            company_id=company_id,
            objective_scope=json.dumps(objective_scope, default=str),
            projects=_dump_list(project_ids),
            employees=_dump_list(employee_ids),
            tasks=_dump_list(task_ids),
            workflows=_dump_list(workflow_ids),
            orchestrations=_dump_list(orchestration_ids),
            verification_policy=json.dumps(verification_policy) if verification_policy else None,
            resource_limits=json.dumps(resource_limits) if resource_limits else None,
            status=status,
        )
        self._db.add(plan)
        self._db.commit()
        for pid in project_ids or []:
            MissionGraphBuilder(self._db).link(
                company_id=company_id,
                source_type="execution_plan",
                source_id=plan.id,
                target_type="startup_project",
                target_id=pid,
                relation=MissionGraphRelation.DEPENDS_ON,
                commit=False,
            )
        self._db.commit()
        self._events.log(
            action=StartupEvents.EXECUTION_PLAN_CREATED,
            company_id=company_id,
            target_type="execution_plan",
            target_id=plan.id,
            details={
                "projects": len(project_ids or []),
                "employees": len(employee_ids or []),
                "tasks": len(task_ids or []),
            },
            outcome="success",
        )
        return plan

    def to_dict(self, plan: ExecutionPlan) -> dict[str, Any]:
        return {
            "id": str(plan.id),
            "company_id": str(plan.company_id),
            "mission_id": str(plan.mission_id),
            "startup_plan_id": str(plan.startup_plan_id) if plan.startup_plan_id else None,
            "objective_scope": _loads(plan.objective_scope),
            "projects": _load_list(plan.projects),
            "employees": _load_list(plan.employees),
            "tasks": _load_list(plan.tasks),
            "workflows": _load_list(plan.workflows),
            "orchestrations": _load_list(plan.orchestrations),
            "verification_policy": _loads(plan.verification_policy),
            "resource_limits": _loads(plan.resource_limits),
            "status": plan.status.value,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
        }


class Executor:
    """Run an execution plan through the existing execution/verification engines."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._verification = VerificationService(db)
        self._recovery = RecoveryService(db)
        self._events = StartupEventLogger(db)
        self._runtime = create_runtime(db)

    def execute_plan(self, plan: ExecutionPlan) -> dict[str, Any]:
        """Execute every task in the plan, verifying and recovering as needed."""
        plan.status = ExecutionPlanStatus.RUNNING
        self._db.commit()
        outcomes: list[dict[str, Any]] = []
        recoveries: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        task_ids = _load_list(plan.tasks)
        for task_id in task_ids:
            outcome = self._execute_task(plan, task_id)
            outcomes.append(outcome)
            if outcome["status"] == "failed":
                recovery = self._recover(plan, task_id, outcome)
                if recovery is not None:
                    recoveries.append(recovery)
                    outcome["recovery"] = recovery
                    outcome["status"] = "recovered"
                else:
                    failures.append({"task_id": str(task_id), **outcome})

        plan.status = ExecutionPlanStatus.COMPLETED if not failures else ExecutionPlanStatus.FAILED
        self._db.commit()
        verified = sum(
            1
            for o in outcomes
            if isinstance(o.get("verification"), dict) and o["verification"].get("status") == "pass"
        )
        return {
            "plan_id": str(plan.id),
            "status": plan.status.value,
            "tasks_executed": len(outcomes),
            "verification_rate": round(verified / len(outcomes), 4) if outcomes else 0.0,
            "recovery_count": len(recoveries),
            "failures": failures,
            "outcomes": outcomes,
            "recoveries": recoveries,
        }

    # ── Internals ─────────────────────────────────────────────────────

    def _execute_task(self, plan: ExecutionPlan, task_id: UUID) -> dict[str, Any]:
        """Run one task through the runtime, then verify its execution."""
        try:
            execution = self._runtime.execute_task(task_id)
        except Exception as exc:  # noqa: BLE001 - surface as failed outcome
            # The runtime persists a failed execution row before raising; find
            # it so downstream recovery runs against the real failed execution.
            execution_id = self._latest_failed_execution_id(task_id)
            return {
                "task_id": str(task_id),
                "status": "failed",
                "error": str(exc),
                "execution_id": str(execution_id) if execution_id else None,
                "verification": None,
            }
        status = "succeeded" if execution.status.value == "succeeded" else "failed"
        self._events.log(
            action=StartupEvents.TASK_EXECUTED,
            company_id=plan.company_id,
            target_type="task",
            target_id=task_id,
            details={"status": status, "execution_id": str(execution.id)},
            outcome="success" if status == "succeeded" else "failed",
        )
        MissionGraphBuilder(self._db).link(
            company_id=plan.company_id,
            source_type="execution",
            source_id=execution.id,
            target_type="task",
            target_id=task_id,
            relation=MissionGraphRelation.EXECUTED_BY,
            commit=False,
        )
        self._db.commit()
        verification = None
        if status == "succeeded":
            try:
                result = self._verification.verify_execution(execution.id)
                verification = (
                    {"id": str(result.id), "status": result.status.value}
                    if result is not None
                    else None
                )
            except Exception as exc:  # noqa: BLE001 - verification must not crash a cycle
                verification = {"error": str(exc)}
        return {
            "task_id": str(task_id),
            "status": status,
            "execution_id": str(execution.id),
            "execution_cost": execution.estimated_cost or 0.0,
            "latency_ms": execution.latency_ms or 0.0,
            "verification": verification,
        }

    def _latest_failed_execution_id(self, task_id: UUID) -> UUID | None:
        from sqlalchemy import select

        from app.db.models.execution import AgentExecution

        row = (
            self._db.execute(
                select(AgentExecution)
                .where(AgentExecution.task_id == task_id)
                .order_by(AgentExecution.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        return row.id if row is not None else None

    def _recover(
        self, plan: ExecutionPlan, task_id: UUID, outcome: dict[str, Any]
    ) -> dict[str, Any] | None:
        execution_id = outcome.get("execution_id")
        if execution_id is None:
            return None
        try:
            attempt = self._recovery.recover(
                UUID(execution_id),
                error_text=outcome.get("error"),
                context={"company_id": str(plan.company_id), "task_id": str(task_id)},
            )
            return {
                "attempt_id": str(attempt.id),
                "outcome": getattr(attempt, "outcome", "unknown"),
                "strategy": getattr(attempt.strategy, "value", attempt.strategy),
            }
        except Exception as exc:  # noqa: BLE001 - recovery failure is also a signal
            return {"outcome": "failed", "error": str(exc)}


def _dump_list(items: list[UUID] | None) -> str | None:
    if not items:
        return None
    return json.dumps([str(i) for i in items])


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _load_list(raw: str | None) -> list[UUID]:
    value = _loads(raw)
    if not isinstance(value, list):
        return []
    return [UUID(str(v)) for v in value if str(v)]
