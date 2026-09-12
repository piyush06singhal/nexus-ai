"""Operating engine — the autonomous cycle that runs and learns.

:class:`OperatingEngine` runs one immutable operating cycle:
OBSERVE → ASSESS → PLAN → PRIORITIZE → ALLOCATE → EXECUTE → VERIFY → MEASURE →
LEARN → REPLAN. Every autonomous action passes :class:`AutonomyService`; the
cycle is capped by ``MAX_AUTONOMOUS_ACTIONS_PER_CYCLE`` and a wall-clock
``startup_max_operating_cycle_duration``; and anything that requires a human is
surfaced as an :class:`ApprovalGate` (the cycle parks at ``blocked`` until an
approved gate continues the work). The ``operating_cycles`` row and its
``stages`` timeline are written once, immutably, at the end.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.company.kpis import KPIService
from app.core.config import settings
from app.db.models.startup import (
    ApprovalGate,
    ApprovalGateType,
    ExecutionPlan,
    OperatingCycle,
    OperatingCycleStatus,
)
from app.db.models.task import Task, TaskStatus
from app.startup.autonomy import AutonomyService
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.execution import ExecutionPlanner, Executor
from app.startup.feedback import FeedbackService
from app.startup.gates import ApprovalGateManager
from app.startup.observe import ObservationLayer
from app.startup.priority import PriorityEngine
from app.startup.replan import ReplanningEngine
from app.startup.types import (
    ApprovalRequiredError,
    AutonomyBlockedError,
    CycleStage,
    StartupEngineError,
)

# Canonical, ordered stage vocabulary for a cycle (for clients to render).
CYCLE_STAGES: tuple[str, ...] = (
    "observe",
    "assess",
    "plan",
    "prioritize",
    "allocate",
    "execute",
    "verify",
    "measure",
    "learn",
    "replan",
)


class OperatingEngine:
    """Run a governed operating cycle for a startup company."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    # ── Public API ────────────────────────────────────────────────────

    def run_cycle(
        self,
        *,
        company_id: UUID,
        mission_id: UUID,
        startup_plan_id: UUID | None = None,
        actor: str = "cycle",
        approved_gate_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Run one full operating cycle; returns the immutable cycle record."""
        company = self._require_active_company(company_id)
        del company
        self._enforce_run_cycle(company_id, approved_gate_id)
        deadline = time.time() + settings.startup_max_operating_cycle_duration * 60

        started = datetime.now(UTC)
        cycle = self._create_cycle(company_id, mission_id, startup_plan_id, started)
        stages: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        recoveries: list[dict[str, Any]] = []
        approvals: list[dict[str, Any]] = []
        snapshot: Any = (
            None  # bound before the try so failure handlers never raise UnboundLocalError
        )

        def stage(name: str, status: str, summary: str | None = None, **metrics: Any) -> None:
            stages.append(
                CycleStage(stage=name, status=status, summary=summary, metrics=metrics).to_dict()
            )

        def checkpoint() -> bool:
            return time.time() > deadline

        try:
            self._events.log(
                action=StartupEvents.CYCLE_STARTED,
                company_id=company_id,
                target_type="operating_cycle",
                target_id=cycle.id,
                details={"cycle_number": cycle.cycle_number},
                outcome="success",
            )

            # OBSERVE
            cycle.status = OperatingCycleStatus.OBSERVING
            observer = ObservationLayer(self._db)
            snapshot = observer.observe(company_id)
            snapshot_row = observer.persist(company_id, snapshot, cycle_id=cycle.id)
            cycle.state_snapshot_id = snapshot_row.id
            stage(
                "observe",
                "completed",
                "Sampled company state from authoritative sources",
                overall_score=snapshot.overall_score,
                task_volume=snapshot.metrics.get("task_volume", 0),
            )

            # ASSESS
            cycle.status = OperatingCycleStatus.ASSESSING
            dims = snapshot.dimensions
            weak = sorted(
                ((k, v) for k, v in dims.items() if k != "risk" and v < 0.7),
                key=lambda kv: kv[1],
            )
            stage(
                "assess",
                "completed",
                "Assessed dimensions; identified weakest areas",
                weak_dimensions=[k for k, _ in weak[:3]],
            )

            # PLAN + PRIORITIZE + ALLOCATE (build the plan, score, record claims)
            cycle.status = OperatingCycleStatus.PLANNING
            plan_context = self._plan_work(company_id, mission_id, startup_plan_id, snapshot)
            projects = plan_context["projects"]
            task_ids = plan_context["task_ids"]
            stage(
                "plan",
                "completed",
                f"Plan covers {len(projects)} active project(s) and {len(task_ids)} task(s)",
                project_count=len(projects),
                task_count=len(task_ids),
            )
            for project in projects:
                result = PriorityEngine(self._db).score(
                    company_id=company_id,
                    target_type="startup_project",
                    target_id=project.id,
                    factors={
                        "strategic_importance": min(1.0, (project.priority or 0) / 5.0 + 0.2),
                        "risk": 1.0 - dims.get("risk", 1.0),
                        "resource_cost": round(1.0 - min(dims.get("budget", 1.0), 1.0), 4),
                    },
                    reason_hint="Operating cycle prioritization from observed state",
                )
                actions.append(
                    {"kind": "prioritize", "target": str(project.id), "score": result.score}
                )
            stage("prioritize", "completed", "Ranked active work by weighted factors")

            # ALLOCATE: budget claims go through autonomy; surface any gate required.
            allocation = self._allocate(company_id, project_ids=[p.id for p in projects])
            if allocation["awaiting_approval"]:
                gate = self._create_gate(
                    company_id,
                    ApprovalGateType.BUDGET_APPROVAL,
                    "allocate_budget",
                    "Cycle budget allocation exceeds the autonomous budget allowance",
                    affected=allocation["requests"],
                    actor=actor,
                )
                approvals.append(
                    {"gate_id": str(gate.id), "action": "allocate_budget", "status": "pending"}
                )
                if not approved_gate_id:
                    stage("allocate", "blocked", "Budget allocation requires human approval")
                    return self._finish(
                        cycle,
                        stages,
                        OperatingCycleStatus.BLOCKED,
                        actions,
                        approvals,
                        failures,
                        recoveries,
                        snapshot,
                        outcome_extra={
                            "blocked_reason": "budget_approval_required",
                            "pending_gate_id": str(gate.id),
                        },
                    )
            stage("allocate", "completed", "Recorded resource allocations for the cycle")

            # EXECUTE
            cycle.status = OperatingCycleStatus.EXECUTING
            execution_plan = self._ensure_execution_plan(
                company_id,
                mission_id,
                startup_plan_id,
                project_ids=[p.id for p in projects],
                task_ids=task_ids,
            )
            if execution_plan is None:
                outcome = {
                    "tasks_executed": 0,
                    "verification_rate": 0.0,
                    "failures": [],
                    "recoveries": [],
                }
                stage("execute", "completed", "No work to execute this cycle")
            else:
                outcome = Executor(self._db).execute_plan(execution_plan)
                actions.append({"kind": "execute_plan", "plan_id": str(execution_plan.id)})
                failures.extend(outcome["failures"])
                recoveries.extend(outcome["recoveries"])
                if checkpoint():
                    return self._finish(
                        cycle,
                        stages,
                        OperatingCycleStatus.BLOCKED,
                        actions,
                        approvals,
                        failures,
                        recoveries,
                        snapshot,
                        outcome_extra={"blocked_reason": "cycle_duration_checkpoint"},
                    )
                stage(
                    "execute",
                    "completed",
                    f"Executed {outcome['tasks_executed']} task(s) with "
                    f"{len(failures)} failure(s), {len(recoveries)} recovery(ies)",
                    tasks_executed=outcome["tasks_executed"],
                    failures=len(failures),
                    recoveries=len(recoveries),
                )

            # VERIFY
            cycle.status = OperatingCycleStatus.VERIFYING
            verification_rate = outcome["verification_rate"]
            stage(
                "verify",
                "completed",
                f"Verification pass rate {verification_rate:.0%} this cycle",
                verification_rate=verification_rate,
                verified=round(verification_rate * max(outcome["tasks_executed"], 1), 2),
            )

            # MEASURE
            cycle.status = OperatingCycleStatus.MEASURING
            kpi_values = self._measure_kpis(company_id)
            measured = ObservationLayer(self._db).observe(company_id)
            stage(
                "measure",
                "completed",
                "Recomputed KPIs and refreshed the state snapshot",
                kpi_count=len(kpi_values),
                overall_score=measured.overall_score,
            )

            # LEARN + REPLAN
            cycle.status = OperatingCycleStatus.REPLANNING
            feedback_records = FeedbackService(self._db).from_state(
                company_id, measured, mission_id=mission_id
            )
            replanner = ReplanningEngine(self._db)
            decision = replanner.evaluate(
                company_id=company_id,
                mission_id=mission_id,
                state=measured,
                execution_outcome=outcome,
            )
            stage(
                "learn",
                "completed",
                f"{len(feedback_records)} feedback record(s) surfaced",
                feedback=len(feedback_records),
            )
            if decision.response.value == "continue":
                stage("replan", "completed", "No replanning trigger; continuing")
            elif decision.requires_approval or self._replan_needs_approval(company_id):
                gate = self._create_gate(
                    company_id,
                    ApprovalGateType.HIGH_RISK_ACTION_APPROVAL
                    if decision.response.value in ("replan", "reduce_scope", "abort_project")
                    else ApprovalGateType.MAJOR_STRATEGIC_CHANGE_APPROVAL,
                    "replan",
                    f"{decision.trigger}: {decision.reason}",
                    affected=[decision.to_dict()],
                    actor=actor,
                )
                approvals.append({"gate_id": str(gate.id), "action": "replan", "status": "pending"})
                stage(
                    "replan",
                    "blocked",
                    f"Replan response '{decision.response.value}' needs approval",
                )
                return self._finish(
                    cycle,
                    stages,
                    OperatingCycleStatus.BLOCKED,
                    actions,
                    approvals,
                    failures,
                    recoveries,
                    measured,
                    outcome_extra={
                        "blocked_reason": "replan_approval_required",
                        "pending_gate_id": str(gate.id),
                        "replan": decision.to_dict(),
                    },
                    decisions=[decision.to_dict()],
                )
            else:
                applied = ReplanningEngine(self._db).apply(
                    company_id=company_id, decision=decision, actor=actor
                )
                stage(
                    "replan",
                    "completed",
                    f"Applied '{decision.response.value}': {applied['applied']}",
                    response=decision.response.value,
                )
                actions.append({"kind": "replan", **decision.to_dict()})

            return self._finish(
                cycle,
                stages,
                OperatingCycleStatus.COMPLETED,
                actions,
                approvals,
                failures,
                recoveries,
                measured,
                outcome_extra={"kpis": kpi_values},
            )

        except ApprovalRequiredError as exc:
            return self._approval_gate_required(cycle, stages, actions, approvals, snapshot, exc)
        except AutonomyBlockedError as exc:
            return self._fail(
                cycle,
                stages,
                actions,
                snapshot,
                reason=f"Autonomy-blocked: {exc.reason}",
            )
        except StartupEngineError as exc:
            return self._fail(cycle, stages, actions, snapshot, reason=str(exc))
        except Exception as exc:  # noqa: BLE001 - cycles must not corrupt their record
            self._db.rollback()
            return self._fail(cycle, stages, actions, snapshot, reason=str(exc))

    # ── Cycle helpers ─────────────────────────────────────────────────

    def _create_cycle(
        self, company_id: UUID, mission_id: UUID, startup_plan_id: UUID | None, started: datetime
    ) -> OperatingCycle:
        number = self._next_cycle_number(company_id)
        cycle = OperatingCycle(
            company_id=company_id,
            mission_id=mission_id,
            startup_plan_id=startup_plan_id,
            cycle_number=number,
            status=OperatingCycleStatus.INITIALIZING,
            stages="[]",
            started_at=started,
        )
        self._db.add(cycle)
        self._db.commit()
        return cycle

    def _next_cycle_number(self, company_id: UUID) -> int:
        current = self._db.scalar(
            select(func.coalesce(func.max(OperatingCycle.cycle_number), 0)).where(
                OperatingCycle.company_id == company_id
            )
        )
        return int(current or 0) + 1

    def _enforce_run_cycle(self, company_id: UUID, approved_gate_id: UUID | None) -> None:
        AutonomyService(self._db).enforce(
            "run_cycle",
            company_id,
            actor="cycle",
            approved_gate_id=approved_gate_id,
        )

    def _require_active_company(self, company_id: UUID):
        from app.db.models.company import Company

        company = self._db.get(Company, company_id)
        if company is None:
            raise StartupEngineError("Company not found")
        if getattr(company.status, "value", company.status) != "active":
            raise StartupEngineError(
                f"Company is {company.status.value}; operating cycles require an active company"
            )
        return company

    def _plan_work(
        self,
        company_id: UUID,
        mission_id: UUID,
        startup_plan_id: UUID | None,
        snapshot: Any,
    ) -> dict[str, Any]:
        """Collect the cycle's work: active projects + their queued tasks."""
        from app.db.models.company import OrganizationalMembership
        from app.db.models.employee import AIEmployee
        from app.startup.projects import ProjectManager

        projects = [
            p
            for p in ProjectManager(self._db).list_(company_id)
            if p.status.value in ("planned", "active", "blocked")
        ]
        memberships = list(
            self._db.execute(
                select(OrganizationalMembership).where(
                    OrganizationalMembership.company_id == company_id
                )
            ).scalars()
        )
        member_ids = [m.employee_id for m in memberships]
        agent_ids: list[UUID] = []
        if member_ids:
            employees = list(
                self._db.execute(select(AIEmployee).where(AIEmployee.id.in_(member_ids))).scalars()
            )
            agent_ids = [e.agent_id for e in employees if e.agent_id is not None]
        task_ids: list[UUID] = []
        if agent_ids:
            tasks = list(
                self._db.execute(
                    select(Task)
                    .where(
                        Task.assigned_agent_id.in_(agent_ids),
                        Task.status.in_([TaskStatus.QUEUED, TaskStatus.IN_PROGRESS]),
                    )
                    .order_by(Task.created_at)
                ).scalars()
            )
            task_ids = [t.id for t in tasks[: settings.startup_max_autonomous_actions_per_cycle]]
        return {
            "projects": projects,
            "task_ids": task_ids,
            "employee_ids": member_ids,
            "agent_ids": agent_ids,
        }

    def _ensure_execution_plan(
        self,
        company_id: UUID,
        mission_id: UUID,
        startup_plan_id: UUID | None,
        *,
        project_ids: list[UUID],
        task_ids: list[UUID],
    ) -> ExecutionPlan | None:
        if not project_ids and not task_ids:
            # An idle cycle needs no execution plan; skip cleanly.
            plan = self._pending_plan(company_id, mission_id)
            return plan
        planner = ExecutionPlanner(self._db)
        plan = planner.create(
            company_id=company_id,
            mission_id=mission_id,
            startup_plan_id=startup_plan_id,
            objective_scope={
                "mission": str(mission_id),
                "projects": [str(p) for p in project_ids],
            },
            project_ids=project_ids,
            task_ids=task_ids,
            verification_policy={"mode": "standard"},
            resource_limits={"max_actions": settings.startup_max_autonomous_actions_per_cycle},
        )
        return plan

    def _pending_plan(self, company_id: UUID, mission_id: UUID) -> ExecutionPlan | None:
        return self._db.scalar(
            select(ExecutionPlan)
            .where(
                ExecutionPlan.company_id == company_id,
                ExecutionPlan.mission_id == mission_id,
            )
            .order_by(ExecutionPlan.created_at.desc())
        )

    def _allocate(self, company_id: UUID, *, project_ids: list[UUID]) -> dict[str, Any]:
        """Record non-budget allocations; budget claims surface as gates."""
        from app.startup.allocate import ResourceAllocator

        allocator = ResourceAllocator(self._db)
        requests: list[dict[str, Any]] = []
        for project_id in project_ids:
            try:
                allocator.allocate(
                    company_id=company_id,
                    target_type="startup_project",
                    target_id=project_id,
                    resource_type="concurrency",
                    amount=1.0,
                    unit="work_unit",
                    purpose={"cycle": "operating"},
                    actor="cycle",
                )
            except ApprovalRequiredError:
                requests.append(
                    {"project_id": str(project_id), "resource_type": "concurrency", "amount": 1.0}
                )
        if requests:
            return {"awaiting_approval": True, "requests": requests}
        return {"awaiting_approval": False, "requests": requests}

    def _measure_kpis(self, company_id: UUID) -> list[dict[str, Any]]:
        kpi_service = KPIService(self._db)
        kpi_service.recompute_all(company_id)
        return [kpi_service.snapshot(k) for k in kpi_service.list_(company_id)]

    def _replan_needs_approval(self, company_id: UUID) -> bool:
        try:
            return not AutonomyService(self._db).can_auto_act("replan", company_id)
        except Exception:  # noqa: BLE001 - default safe
            return True

    # ── Gates / finishing ─────────────────────────────────────────────

    def _create_gate(
        self,
        company_id: UUID,
        gate_type: ApprovalGateType,
        action: str,
        rationale: str,
        *,
        affected: list[Any] | None = None,
        actor: str = "cycle",
    ) -> ApprovalGate:
        return ApprovalGateManager(self._db).create(
            company_id=company_id,
            gate_type=gate_type,
            requested_action={"action": action, "source": "operating_cycle", "actor": actor},
            rationale=rationale,
            risk_level="high",
            affected_entities=[
                a if isinstance(a, dict) else {"detail": str(a)} for a in (affected or [])
            ],
        )

    def _approval_gate_required(
        self,
        cycle: OperatingCycle,
        stages: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        approvals: list[dict[str, Any]],
        snapshot: Any,
        exc: ApprovalRequiredError,
    ) -> dict[str, Any]:
        gate = self._create_gate(
            cycle.company_id,
            ApprovalGateType.HIGH_RISK_ACTION_APPROVAL,
            exc.action,
            exc.reason,
            actor="cycle",
        )
        approvals.append({"gate_id": str(gate.id), "action": exc.action, "status": "pending"})
        stages.append(
            CycleStage(
                stage="approval",
                status="blocked",
                summary=f"'{exc.action}' requires human approval: {exc.reason}",
                pending_gate=str(gate.id),
            ).to_dict()
        )
        return self._finish(
            cycle,
            stages,
            OperatingCycleStatus.BLOCKED,
            actions,
            approvals,
            [],
            [],
            snapshot,
            outcome_extra={"blocked_reason": "approval_required", "pending_gate_id": str(gate.id)},
        )

    def _finish(
        self,
        cycle: OperatingCycle,
        stages: list[dict[str, Any]],
        status: OperatingCycleStatus,
        actions: list[dict[str, Any]],
        approvals: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        recoveries: list[dict[str, Any]],
        snapshot: Any,
        *,
        outcome_extra: dict[str, Any] | None = None,
        decisions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        cycle.status = status
        cycle.stages = json.dumps(stages, default=str)
        cycle.ended_at = datetime.now(UTC)
        cycle.actions = json.dumps(actions, default=str) or None
        cycle.decisions = json.dumps(decisions or [], default=str) or None
        cycle.failures = json.dumps(failures, default=str) or None
        cycle.recovery = json.dumps(recoveries, default=str) or None
        cycle.approvals = json.dumps(approvals, default=str) or None
        cycle.kpis = json.dumps(outcome_extra.get("kpis", []), default=str) or None
        outcome = {
            "status": status.value,
            "overall_score": snapshot.overall_score if snapshot is not None else None,
        }
        outcome.update(outcome_extra or {})
        cycle.outcome = json.dumps(outcome, default=str)
        self._db.commit()
        if status == OperatingCycleStatus.COMPLETED:
            self._events.log(
                action=StartupEvents.CYCLE_COMPLETED,
                company_id=cycle.company_id,
                target_type="operating_cycle",
                target_id=cycle.id,
                details={
                    "cycle_number": cycle.cycle_number,
                    "overall_score": snapshot.overall_score if snapshot is not None else None,
                    "stages": len(stages),
                },
                outcome="success",
            )
        elif status == OperatingCycleStatus.BLOCKED:
            self._events.log(
                action=StartupEvents.CYCLE_BLOCKED,
                company_id=cycle.company_id,
                target_type="operating_cycle",
                target_id=cycle.id,
                details={
                    "cycle_number": cycle.cycle_number,
                    "reason": outcome_extra.get("blocked_reason"),
                },
                outcome="blocked",
            )
        self._db.commit()
        return self.to_dict(cycle, stages=stages)

    def _fail(
        self,
        cycle: OperatingCycle,
        stages: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        snapshot: Any,
        reason: str,
    ) -> dict[str, Any]:
        return self._finish(
            cycle,
            stages,
            OperatingCycleStatus.FAILED,
            actions,
            [],
            [],
            [],
            snapshot,
            outcome_extra={"error": reason},
        )

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(
        self, cycle: OperatingCycle, *, stages: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        return {
            "id": str(cycle.id),
            "company_id": str(cycle.company_id),
            "mission_id": str(cycle.mission_id) if cycle.mission_id else None,
            "startup_plan_id": str(cycle.startup_plan_id) if cycle.startup_plan_id else None,
            "cycle_number": cycle.cycle_number,
            "status": cycle.status.value,
            "stages": stages or _loads_json(cycle.stages) or [],
            "state_snapshot_id": str(cycle.state_snapshot_id) if cycle.state_snapshot_id else None,
            "decisions": _loads_json(cycle.decisions) or [],
            "actions": _loads_json(cycle.actions) or [],
            "kpis": _loads_json(cycle.kpis) or [],
            "failures": _loads_json(cycle.failures) or [],
            "recovery": _loads_json(cycle.recovery) or [],
            "approvals": _loads_json(cycle.approvals) or [],
            "outcome": _loads_json(cycle.outcome) or {},
            "started_at": cycle.started_at.isoformat() if cycle.started_at else None,
            "ended_at": cycle.ended_at.isoformat() if cycle.ended_at else None,
        }

    def get_cycle(self, company_id: UUID, cycle_id: UUID) -> dict[str, Any] | None:
        cycle = self._db.get(OperatingCycle, cycle_id)
        if cycle is None or cycle.company_id != company_id:
            return None
        return self.to_dict(cycle)

    def list_cycles(self, company_id: UUID, *, limit: int = 20) -> list[dict[str, Any]]:
        stmt = (
            select(OperatingCycle)
            .where(OperatingCycle.company_id == company_id)
            .order_by(OperatingCycle.cycle_number.desc())
            .limit(limit)
        )
        return [self.to_dict(c) for c in self._db.execute(stmt).scalars().all()]


def _loads_json(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
