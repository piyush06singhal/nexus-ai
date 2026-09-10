"""Multi-agent orchestration engine.

The :class:`Orchestrator` drives a single orchestration run end-to-end,
mirroring the :class:`app.workflow.engine.WorkflowEngine` shape: synchronous,
testable against SQLite, no HTTP/Redis/external calls. It reuses the existing
AgentRuntime (Phase 1/2/4) inside a bounded thread pool rather than owning any
agent logic.

Pipeline::

    CREATED → PLANNING → PLANNED → ASSIGNING → RUNNING → SYNTHESIZING → terminal
    1. Load orchestration; validate CREATED/RUNNING state.
    2. PLANNING → PLANNED: planner produces a validated ExecutionPlan; persist
       tasks + execution_graph.
    3. PLANNED → ASSIGNING: capability-select an agent per task; persist
       assignments + task.agent_id. No runnable task → orchestration FAILED.
    4. ASSIGNING → RUNNING: run ready tasks in a bounded ThreadPoolExecutor.
       Each worker uses a **fresh session** (mirroring the workflow worker
       pattern) so SQLite StaticPool + check_same_thread=False stays safe.
       A failed task marks its dependents skipped; independent tasks continue.
    5. RUNNING → SYNTHESIZING: aggregate results → ConflictDetector →
       ResultSynthesizer → persist final_result + metrics.
    6. → COMPLETED / PARTIALLY_COMPLETED / FAILED / CANCELLED.

All status changes pass through :mod:`app.orchestration.state_machine`. Limits
come from :class:`app.orchestration.policies.OrchestrationLimits`.
"""

from __future__ import annotations

import json
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.core.logging import get_logger
from app.db.models.agent import Agent
from app.db.models.orchestration import (
    AgentAssignment,
    AgentMessageType,
    AssignmentStatus,
    Orchestration,
    OrchestrationResult,
    OrchestrationStatus,
    OrchestrationTask,
    OrchestrationTaskStatus,
)
from app.orchestration.conflicts import NumericConflictDetector
from app.orchestration.context import build_assignment_context, upsert_shared_context
from app.orchestration.messages import AgentMessagePayload
from app.orchestration.planner import DeterministicPlanner
from app.orchestration.policies import OrchestrationLimits
from app.orchestration.selector import CapabilityAgentSelector
from app.orchestration.state_machine import (
    transition_assignment,
    transition_orchestration,
    transition_task,
)
from app.orchestration.synthesizer import ResultSynthesizer
from app.orchestration.types import (
    NoAgentAvailableError,
    OrchestrationError,
    PlanTask,
)
from app.runtime.runtime import AgentRuntime
from app.schemas.task import TaskCreate
from app.services.agent_service import AgentService
from app.services.execution_service import ExecutionService
from app.services.task_service import TaskService

logger = get_logger(__name__)


def _loads(raw: str | None):
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _dumps(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OrchestratorError(Exception):
    """Base exception for orchestration engine failures."""


class OrchestratorCancelledError(OrchestratorError):
    """The orchestration was cancelled mid-run."""


class Orchestrator:
    """Drives a single orchestration run to a terminal status."""

    def __init__(
        self,
        session_factory,
        *,
        planner=None,
        selector=None,
        synthesizer=None,
        conflict_detector=None,
        limits: OrchestrationLimits | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._planner = planner or DeterministicPlanner()
        self._selector = selector or CapabilityAgentSelector()
        self._synthesizer = synthesizer or ResultSynthesizer()
        self._conflicts = conflict_detector or NumericConflictDetector()
        self._limits = limits or OrchestrationLimits.from_settings(app_settings)

    # ── Public entry point ────────────────────────────────────────────────────

    def execute(self, orchestration: Orchestration, db: Session) -> Orchestration:
        """Run *orchestration* to completion using *db* as the control session.

        Mirrors :meth:`WorkflowEngine.execute` error handling; the returned
        :class:`Orchestration` is refreshed and terminal.
        """
        try:
            result = self._run(orchestration, db)
            orchestration.final_result = _dumps(result)
            terminal = self._final_status(db, orchestration)
            orchestration.status = terminal
        except OrchestratorCancelledError:
            orchestration.status = OrchestrationStatus.CANCELLED
            orchestration.error = "Orchestration was cancelled"
        except OrchestrationError as exc:
            orchestration.status = OrchestrationStatus.FAILED
            orchestration.error = str(exc)
        except Exception as exc:  # defensive — surface unexpected failures cleanly
            logger.exception(
                "orchestration_failed",
                extra={"orchestration_id": str(orchestration.id), "error": str(exc)},
            )
            orchestration.status = OrchestrationStatus.FAILED
            orchestration.error = f"Unexpected error: {exc}"

        now = _utcnow()
        orchestration.completed_at = now
        started = orchestration.started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        if started is not None:
            orchestration.duration_ms = int((now - started).total_seconds() * 1000)
        db.commit()
        db.refresh(orchestration)
        return orchestration

    # ── Core run ──────────────────────────────────────────────────────────────

    def _run(self, orchestration: Orchestration, db: Session) -> dict:
        """Execute the full lifecycle, returning the synthesized final result."""
        # Validate entry state.
        current = orchestration.status
        if current in (OrchestrationStatus.CREATED,):
            pass
        elif current == OrchestrationStatus.RUNNING:
            # Resumption: tasks already running/complete are handled below.
            pass
        else:
            raise OrchestratorError(
                f"Cannot execute orchestration in {current.value!r} status "
                "(must be created or running)"
            )

        if orchestration.started_at is None:
            orchestration.started_at = _utcnow()
        self._set_status(db, orchestration, OrchestrationStatus.PLANNING)

        # ── PLANNING ──────────────────────────────────────────────────────────
        plan = self._plan(orchestration, db)

        # ── ASSIGNING ─────────────────────────────────────────────────────────
        self._set_status(db, orchestration, OrchestrationStatus.ASSIGNING)
        self._assign(orchestration, db, plan.tasks)

        # ── RUNNING ──────────────────────────────────────────────────────────
        self._set_status(db, orchestration, OrchestrationStatus.RUNNING)
        tasks = self._load_tasks(db, orchestration.id)
        plan_stats = self._execute_tasks(orchestration, db, tasks, plan.tasks)

        if orchestration.status == OrchestrationStatus.CANCELLED:
            raise OrchestratorCancelledError("Orchestration cancelled during execution")

        # ── SYNTHESIZING ──────────────────────────────────────────────────────
        self._set_status(db, orchestration, OrchestrationStatus.SYNTHESIZING)
        result = self._synthesize(db, orchestration, tasks)
        orchestration.metrics = _dumps(plan_stats)
        return result

    # ── Planning ──────────────────────────────────────────────────────────────

    def _plan(self, orchestration: Orchestration, db: Session):
        objective = orchestration.objective
        agents = self._load_agents(db)
        try:
            plan = self._planner.create_plan(objective, agents, {})
        except OrchestrationError as exc:
            raise OrchestratorError(f"Planning failed: {exc}") from exc
        if len(plan.tasks) > self._limits.max_tasks:
            raise OrchestratorError(
                f"Plan has {len(plan.tasks)} tasks, exceeding max of {self._limits.max_tasks}"
            )

        # Persist tasks + execution graph.
        execution_graph = {
            "tasks": [t.name for t in plan.tasks],
            "dependencies": {t.name: t.dependencies for t in plan.tasks},
        }
        orchestration.execution_graph = _dumps(execution_graph)
        orchestration.selected_agents = _dumps([])
        for _i, task in enumerate(plan.tasks):
            row = OrchestrationTask(
                orchestration_id=orchestration.id,
                name=task.name,
                description=task.description,
                required_capabilities=_dumps(task.required_capabilities),
                dependencies=_dumps(task.dependencies),
                status=OrchestrationTaskStatus.PENDING,
                attempt_number=1,
            )
            db.add(row)
        self._set_status(db, orchestration, OrchestrationStatus.PLANNED)
        orchestration.strategy = plan.strategy
        db.commit()
        db.refresh(orchestration)
        return plan

    # ── Assignment ────────────────────────────────────────────────────────────

    def _assign(self, orchestration: Orchestration, db: Session, tasks: list[PlanTask]) -> None:
        agents = self._load_agents(db)
        assigned_agents: list[str] = []
        assign_map: dict[str, UUID] = {}
        any_runnable = False
        for task in tasks:
            try:
                selection = self._selector.select(task, agents, db)
            except NoAgentAvailableError as exc:
                # No agent can run this task — fail it (and its dependents).
                logger.warning(
                    "task_no_agent",
                    extra={
                        "orchestration_id": str(orchestration.id),
                        "task": task.name,
                        "error": str(exc),
                    },
                )
                self._mark_task_unassignable(db, orchestration.id, task.name, str(exc))
                continue
            row = (
                db.query(OrchestrationTask)
                .filter(
                    OrchestrationTask.orchestration_id == orchestration.id,
                    OrchestrationTask.name == task.name,
                )
                .one()
            )
            row.agent_id = selection.agent_id
            row.status = transition_task(row.status, OrchestrationTaskStatus.READY)
            assignment = AgentAssignment(
                orchestration_id=orchestration.id,
                task_id=row.id,
                agent_id=selection.agent_id,
                role=selection.role,
                instructions=task.description,
                dependencies=_dumps(task.dependencies),
                status=AssignmentStatus.ASSIGNED,
                priority=0,
                attempt_number=1,
            )
            db.add(assignment)
            assigned_agents.append(str(selection.agent_id))
            assign_map[task.name] = selection.agent_id
            any_runnable = True
        orchestration.selected_agents = _dumps(assigned_agents)
        db.commit()

        if not any_runnable:
            raise OrchestratorError("No task could be assigned an available agent")

    # ── Execution ─────────────────────────────────────────────────────────────

    def _execute_tasks(
        self,
        orchestration: Orchestration,
        db: Session,
        tasks: list[OrchestrationTask],
        plan_tasks: list[PlanTask],
    ) -> dict:
        """Run ready tasks on a bounded thread pool, honoring dependencies."""
        max_parallel = min(
            self._limits.max_parallel_agents,
            self._limits.max_parallel_tasks,
            len(tasks) or 1,
        )
        deadline = _utcnow().timestamp() + self._limits.max_execution_duration_seconds

        # In-memory status tracking keyed by task name.
        status: dict[str, OrchestrationTaskStatus] = {t.name: t.status for t in tasks}
        deps: dict[str, list[str]] = {}
        for t in tasks:
            raw = t.dependencies
            parsed = _loads(raw) if isinstance(raw, str) else (raw or [])
            deps[t.name] = [str(d.decode()) if isinstance(d, bytes) else d for d in parsed]

        results: dict[str, dict] = {}
        failures: dict[str, str] = {}
        stats = {
            "tasks_total": len(tasks),
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tasks_skipped": 0,
            "messages": 0,
            "parallelism": max_parallel,
        }

        pool = ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="orch-task")
        futures: dict[Future, str] = {}
        iterations = 0

        try:
            while True:
                iterations += 1
                if iterations > self._limits.max_execution_iterations:
                    raise OrchestratorError("Orchestration exceeded maximum execution iterations")

                # Observe cancellation from the control session.
                db.refresh(orchestration)
                if orchestration.status == OrchestrationStatus.CANCELLED:
                    for name in list(status):
                        status[name] = OrchestrationTaskStatus.CANCELLED
                    break
                if _utcnow().timestamp() > deadline:
                    # Hard time budget exceeded.
                    for name, stat in list(status.items()):
                        if stat not in (
                            OrchestrationTaskStatus.COMPLETED,
                            OrchestrationTaskStatus.FAILED,
                        ):
                            status[name] = OrchestrationTaskStatus.CANCELLED
                    break

                # Advance PENDING -> READY/SKIPPED based on dependency outcomes.
                for name in deps:
                    if status[name] != OrchestrationTaskStatus.PENDING:
                        continue
                    unmet = [
                        d
                        for d in deps[name]
                        if d in status
                        and status[d]
                        not in (
                            OrchestrationTaskStatus.COMPLETED,
                            OrchestrationTaskStatus.SKIPPED,
                        )
                    ]
                    dep_failed = any(
                        d in status and status[d] == OrchestrationTaskStatus.FAILED
                        for d in deps[name]
                    )
                    if dep_failed or (deps[name] and unmet):
                        if dep_failed:
                            status[name] = OrchestrationTaskStatus.SKIPPED
                            stats["tasks_skipped"] += 1
                        # else still blocked; wait for deps.
                        continue
                    status[name] = OrchestrationTaskStatus.READY

                # Submit READY tasks up to the parallelism cap.
                ready = sorted(
                    [
                        name
                        for name, stat in status.items()
                        if stat == OrchestrationTaskStatus.READY
                    ],
                )
                for name in ready:
                    if len(futures) >= max_parallel:
                        break
                    fut = pool.submit(self._run_task, orchestration.id, name)
                    futures[fut] = name
                    status[name] = OrchestrationTaskStatus.RUNNING

                if not futures:
                    # No running tasks. If all terminal, we're done.
                    if all(
                        stat
                        in (
                            OrchestrationTaskStatus.COMPLETED,
                            OrchestrationTaskStatus.FAILED,
                            OrchestrationTaskStatus.SKIPPED,
                            OrchestrationTaskStatus.CANCELLED,
                        )
                        for stat in status.values()
                    ):
                        break
                    # Otherwise: cycle that cannot progress (shouldn't happen).
                    raise OrchestratorError(
                        "Orchestration stalled: no runnable task and not all terminal"
                    )

                # Wait for at least one task to finish.
                done, _ = wait(list(futures), return_when=FIRST_COMPLETED)
                for fut in done:
                    name = futures.pop(fut)
                    try:
                        outcome = fut.result()
                    except Exception as exc:  # worker raised unexpectedly
                        outcome = {
                            "name": name,
                            "successful": False,
                            "error": f"Worker error: {exc}",
                        }
                    if outcome["successful"]:
                        status[name] = OrchestrationTaskStatus.COMPLETED
                        results[name] = outcome
                        stats["tasks_completed"] += 1
                        self._post_message(
                            db,
                            orchestration.id,
                            AgentMessageType.TASK_RESULT,
                            f"Task {name!r} completed by agent {outcome.get('agent_id')}.",
                        )
                        stats["messages"] += 1
                    else:
                        status[name] = OrchestrationTaskStatus.FAILED
                        failures[name] = outcome.get("error", "unknown error")
                        stats["tasks_failed"] += 1
                        self._post_message(
                            db,
                            orchestration.id,
                            AgentMessageType.ERROR,
                            f"Task {name!r} failed: {outcome.get('error')}",
                        )
                        stats["messages"] += 1

                # Persist cumulative statuses for the orchestration's tasks so the
                # UI/graph reflects progress after each batch.
                self._sync_task_statuses(db, orchestration.id, status)
        finally:
            pool.shutdown(wait=True)

        stats["tasks_cancelled"] = sum(
            1 for stat in status.values() if stat == OrchestrationTaskStatus.CANCELLED
        )
        return stats

    def _run_task(self, orchestration_id: UUID, task_name: str) -> dict:
        """Execute a single task in its own session via AgentRuntime.

        Returns a plain dict outcome; never raises across the thread boundary
        (callers handle re-raise). Persists task/assignment/result in its own
        fresh session.
        """
        fresh: Session = self._session_factory()
        task: OrchestrationTask | None = None
        try:
            task = (
                fresh.query(OrchestrationTask)
                .filter(
                    OrchestrationTask.orchestration_id == orchestration_id,
                    OrchestrationTask.name == task_name,
                )
                .one()
            )
            assignment = (
                fresh.query(AgentAssignment).filter(AgentAssignment.task_id == task.id).one()
            )
            agent = fresh.get(Agent, assignment.agent_id)
            if agent is None:
                raise OrchestratorError(f"Assigned agent {assignment.agent_id} not found")

            task.status = transition_task(task.status, OrchestrationTaskStatus.RUNNING)
            assignment.status = transition_assignment(assignment.status, AssignmentStatus.RUNNING)
            task.started_at = _utcnow()
            assignment.started_at = _utcnow()
            fresh.commit()

            # Build the assignment context (selective, shared + prior results).
            completed = (
                fresh.query(OrchestrationResult)
                .filter(OrchestrationResult.orchestration_id == orchestration_id)
                .all()
            )
            ctx = build_assignment_context(
                fresh.get(Orchestration, orchestration_id), task, completed, db=fresh
            )

            # Run via the existing Agent Runtime (creates a temporary Task).
            task_svc = TaskService(fresh)
            tmp = task_svc.create(
                TaskCreate(
                    title=f"orchestration:{task.name}",
                    input_data=ctx,
                    assigned_agent_id=agent.id,
                )
            )
            task_svc.assign(tmp.id, agent.id)
            runtime = AgentRuntime(
                agent_service=AgentService(fresh),
                task_service=task_svc,
                execution_service=ExecutionService(fresh),
            )
            execution = runtime.execute_task(tmp.id)
            output = _loads(execution.output_data)
            structured = output.get("output", {})
            summary = output.get("summary", execution.output_data or "")
            confidence = output.get("confidence")

            # Optional per-task verification (Phase 6, §27): if the orchestration
            # declares a verification policy, verify the task's structured output
            # and fail the task on a below-threshold verdict so the orchestrator's
            # dependency/fallback logic applies.
            orchestrator_row = fresh.get(Orchestration, orchestration_id)
            vp_cfg = _loads(orchestrator_row.verification_policy) if orchestrator_row else {}
            if vp_cfg and vp_cfg.get("required", True):
                self._verify_task(fresh, task, structured, vp_cfg, orchestration_id)

            result = OrchestrationResult(
                orchestration_id=orchestration_id,
                task_id=task.id,
                assignment_id=assignment.id,
                agent_id=agent.id,
                content=execution.output_data or summary,
                structured_data=_dumps(structured),
                confidence=confidence,
                metadata_json=_dumps({"task_name": task.name}),
            )
            fresh.add(result)

            assignment.output_data = _dumps(structured)
            assignment.status = transition_assignment(assignment.status, AssignmentStatus.COMPLETED)
            assignment.agent_execution_id = execution.id
            assignment.completed_at = _utcnow()

            task.output_data = _dumps(structured)
            task.result_summary = summary
            task.status = transition_task(task.status, OrchestrationTaskStatus.COMPLETED)
            task.completed_at = _utcnow()

            # Mirror the structured facts into the shared orchestration context.
            if structured:
                for key in list(structured)[:8]:
                    upsert_shared_context(
                        fresh,
                        orchestration_id,
                        f"task.{task_name}.{key}",
                        structured[key],
                        kind="intermediate_result",
                    )

            fresh.commit()
            return {
                "name": task_name,
                "successful": True,
                "agent_id": str(agent.id),
                "structured": structured,
                "summary": summary,
                "confidence": confidence,
            }
        except Exception as exc:
            if task is not None:
                task.status = transition_task(task.status, OrchestrationTaskStatus.FAILED)
                task.error = str(exc)
                task.completed_at = _utcnow()
                assignment = (
                    fresh.query(AgentAssignment).filter(AgentAssignment.task_id == task.id).first()
                )
                if assignment is not None:
                    assignment.status = transition_assignment(
                        assignment.status, AssignmentStatus.FAILED
                    )
                    assignment.error = str(exc)
                    assignment.completed_at = _utcnow()
                fresh.commit()
            logger.warning(
                "orchestration_task_failed", extra={"task": task_name, "error": str(exc)}
            )
            return {"name": task_name, "successful": False, "error": str(exc)}
        finally:
            fresh.close()

    # ── Verification ───────────────────────────────────────────────────────────

    def _verify_task(
        self,
        db: Session,
        task: OrchestrationTask,
        structured: dict,
        vp_cfg: dict,
        orchestration_id: UUID,
    ) -> None:
        """Verify a task's structured output against the orchestration policy (§27).

        Uses the shared :class:`VerificationService` — the orchestrator never
        re-implements verification.  A below-threshold or FAIL verdict raises so
        the task (and its dependents) are marked failed and recover independently
        without restarting unrelated agents.
        """
        from app.verification.policy import VerificationPolicy
        from app.verification.service import VerificationService

        if not structured:
            raise OrchestratorError(
                f"Task {task.name!r}: empty structured output cannot be verified"
            )
        try:
            policy = VerificationPolicy.from_dict(vp_cfg)
        except ValueError as exc:
            raise OrchestratorError(
                f"Task {task.name!r}: invalid verification_policy: {exc}"
            ) from exc
        if not policy.required:
            return

        result = VerificationService(db).verify(
            structured,
            policy=policy,
            orchestration_id=orchestration_id,
            context={"criteria": vp_cfg.get("criteria", [])},
            risk_level=vp_cfg.get("risk_level", "high"),
        )
        below_min = result.score is not None and result.score < policy.minimum_score
        if result.status.value in ("fail", "uncertain") or below_min:
            raise OrchestratorError(
                f"Task {task.name!r} failed verification (status={result.status.value}, "
                f"score={result.score:.2f})"
            )

    # ── Synthesis ─────────────────────────────────────────────────────────────

    def _synthesize(
        self,
        db: Session,
        orchestration: Orchestration,
        tasks: list[OrchestrationTask],
    ) -> dict:
        results = (
            db.query(OrchestrationResult)
            .filter(OrchestrationResult.orchestration_id == orchestration.id)
            .all()
        )
        if not results:
            raise OrchestratorError("No agent produced a result — nothing to synthesize")
        conflicts = self._conflicts.detect(results)
        final = self._synthesizer.synthesize(orchestration, results, tasks, conflicts=conflicts)
        # Record conflicts to the shared context for visibility.
        if conflicts:
            upsert_shared_context(
                db,
                orchestration.id,
                "conflicts",
                [c.__dict__ for c in conflicts],
                kind="decision",
            )
        return final

    def _final_status(self, db: Session, orchestration: Orchestration) -> OrchestrationStatus:
        """Pick the terminal status for an orchestration after execution."""
        if orchestration.status == OrchestrationStatus.CANCELLED:
            return orchestration.status
        tasks = (
            db.query(OrchestrationTask)
            .filter(OrchestrationTask.orchestration_id == orchestration.id)
            .all()
        )
        completed = sum(1 for t in tasks if t.status == OrchestrationTaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == OrchestrationTaskStatus.FAILED)
        if completed and not failed and completed == len(tasks):
            return OrchestrationStatus.COMPLETED
        if completed > 0 and failed > 0:
            return OrchestrationStatus.PARTIALLY_COMPLETED
        if completed > 0:
            return OrchestrationStatus.PARTIALLY_COMPLETED
        return OrchestrationStatus.FAILED

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, db: Session, orchestration: Orchestration, status) -> None:
        orchestration.status = transition_orchestration(orchestration.status, status)
        db.commit()
        db.refresh(orchestration)

    def _load_agents(self, db: Session) -> list[Agent]:
        return db.query(Agent).all()

    def _load_tasks(self, db: Session, orchestration_id: UUID) -> list[OrchestrationTask]:
        return (
            db.query(OrchestrationTask)
            .filter(OrchestrationTask.orchestration_id == orchestration_id)
            .all()
        )

    def _mark_task_unassignable(
        self, db: Session, orchestration_id: UUID, name: str, error: str
    ) -> None:
        row = (
            db.query(OrchestrationTask)
            .filter(
                OrchestrationTask.orchestration_id == orchestration_id,
                OrchestrationTask.name == name,
            )
            .one()
        )
        row.status = transition_task(row.status, OrchestrationTaskStatus.FAILED)
        row.error = error
        db.commit()

    def _post_message(
        self, db: Session, orchestration_id: UUID, mtype: AgentMessageType, content: str
    ) -> None:
        from app.orchestration.bus import AgentMessageBus

        AgentMessageBus(db).send(
            AgentMessagePayload(
                orchestration_id=orchestration_id,
                message_type=mtype,
                content=content,
                sender_agent_id=None,  # system/orchestrator
                recipient_agent_id=None,  # broadcast
            )
        )

    def _sync_task_statuses(self, db: Session, orchestration_id: UUID, status: dict) -> None:
        """Push in-memory task statuses to the DB so the graph stays live."""
        rows = (
            db.query(OrchestrationTask)
            .filter(OrchestrationTask.orchestration_id == orchestration_id)
            .all()
        )
        for row in rows:
            target = status.get(row.name)
            if target is not None and target != row.status:
                try:
                    row.status = transition_task(row.status, target)
                except OrchestrationError:
                    # Already terminal / not a legal move — leave it.
                    pass
        db.commit()
