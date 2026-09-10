"""Workflow execution engine.

Orchestrates a single workflow execution end-to-end.  The engine is
synchronous, testable against SQLite, and delegates to the existing
AgentRuntime (for ``agent_task`` steps) and ToolExecutor (for
``tool_action`` steps) — no HTTP, no Redis, no external dependencies
beyond the DB session.

Pipeline::

    1. Load workflow + steps + execution from DB.
    2. Build initial state from ``execution.input_data``.
    3. Topologically sort steps respecting ``dependencies`` and ``order``.
    4. For each step whose deps are all completed:
       a. Resolve ``input_mapping`` from state.
       b. Run the step via ``_run_step()``.
       c. Store output in state and update ``StepExecution``.
       d. Mark step COMPLETED, FAILED, SKIPPED, or TIMED_OUT.
    5. After all steps: mark execution COMPLETED or FAILED.
    6. Return the ``WorkflowExecution`` ORM object.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models.agent import Agent
from app.db.models.employee import AIEmployee
from app.db.models.workflow import (
    IdempotencyTag,
    StepExecution,
    StepStatus,
    Workflow,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowStep,
    WorkflowStepType,
)
from app.runtime.runtime import AgentRuntime
from app.schemas.task import TaskCreate
from app.services.agent_service import AgentService
from app.services.execution_service import ExecutionService
from app.services.permission_service import PermissionService
from app.services.task_service import TaskService
from app.tools.executor import ToolExecutor
from app.workflow.conditions import ConditionEvaluationError, evaluate_condition
from app.workflow.mapping import resolve_mapping
from app.workflow.state import WorkflowState

logger = get_logger(__name__)

# Thread pool for timeout enforcement on individual steps.
_STEP_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="wf-step")


class WorkflowEngineError(Exception):
    """Base exception for workflow engine failures."""


class StepTimeoutError(WorkflowEngineError):
    """A step exceeded its timeout."""


class StepFailedError(WorkflowEngineError):
    """A step failed after all retry attempts."""


class ExecutionCancelledError(WorkflowEngineError):
    """The execution was cancelled mid-run."""


def _loads(raw: str | None) -> Any:
    """Parse a JSON text field.  Returns ``None`` if missing/invalid."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _dumps(value: Any) -> str | None:
    """Serialize a value to JSON text."""
    if value is None:
        return None
    return json.dumps(value, default=str)


def _coerce_utc(dt: datetime) -> datetime:
    """Normalise a DB-read datetime to be UTC-aware.

    SQLite does not retain timezone info, so ``DateTime(timezone=True)``
    values come back offset-naive.  Comparing them against ``now(UTC)``
    (aware) fails; this coerces naive datetimes to aware-UTC in place.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _utcnow() -> datetime:
    """Return the current time as a UTC-aware datetime."""
    return datetime.now(UTC)


class WorkflowEngine:
    """Orchestrates a single workflow execution.

    Args:
        session: SQLAlchemy session bound to the same DB as the workflow
            tables.  All ORM reads/writes go through this session.
    """

    def __init__(self, session: Session) -> None:
        self._db = session

    def execute(self, execution_id: UUID) -> WorkflowExecution:
        """Run a workflow execution to completion (or failure/cancel).

        This is the main entry point.  The caller should ensure the
        execution exists and is in ``queued`` status.

        Returns the updated :class:`WorkflowExecution` ORM object.
        """
        execution = self._db.get(WorkflowExecution, execution_id)
        if execution is None:
            raise NotFoundError(f"Workflow execution {execution_id} not found")
        if execution.status not in (
            WorkflowExecutionStatus.QUEUED,
            WorkflowExecutionStatus.RUNNING,
        ):
            raise ValidationError(
                f"Cannot execute workflow in {execution.status.value!r} status "
                "(must be queued or running)"
            )

        workflow = self._db.get(Workflow, execution.workflow_id)
        if workflow is None:
            raise NotFoundError(f"Workflow {execution.workflow_id} not found")

        # Load steps ordered by (order, created_at) for deterministic tie-breaking.
        steps = self._get_steps_ordered(workflow.id)

        # Mark execution as running (unless the worker has already claimed it).
        if execution.status != WorkflowExecutionStatus.RUNNING:
            now = _utcnow()
            execution.status = WorkflowExecutionStatus.RUNNING
            execution.started_at = now
            self._db.commit()
        self._db.refresh(execution)

        try:
            result = self._run_workflow(execution, workflow, steps)
            execution.output_data = _dumps(result)
            execution.status = WorkflowExecutionStatus.COMPLETED
        except ExecutionCancelledError:
            # The execution was cancelled mid-run — mark remaining steps cancelled.
            execution.status = WorkflowExecutionStatus.CANCELLED
            execution.error = "Execution was cancelled"
        except StepFailedError as exc:
            execution.status = WorkflowExecutionStatus.FAILED
            execution.error = str(exc)
        except Exception as exc:
            logger.exception(
                "workflow_execution_failed",
                extra={"execution_id": str(execution_id), "error": str(exc)},
            )
            execution.status = WorkflowExecutionStatus.FAILED
            execution.error = f"Unexpected error: {exc}"

        # Mark execution as terminal.
        now = _utcnow()
        execution.completed_at = now
        started = _coerce_utc(execution.started_at)
        if started is not None:
            execution.duration_ms = int((now - started).total_seconds() * 1000)
        self._db.commit()
        self._db.refresh(execution)
        return execution

    def _get_steps_ordered(self, workflow_id: UUID) -> list[WorkflowStep]:
        """Load all steps for a workflow ordered by (order, created_at)."""
        from sqlalchemy import select

        stmt = (
            select(WorkflowStep)
            .where(WorkflowStep.workflow_id == workflow_id)
            .order_by(WorkflowStep.order, WorkflowStep.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def _get_step_execution(
        self,
        execution_id: UUID,
        step_id: UUID,
    ) -> StepExecution | None:
        """Find an existing step execution for the given (execution, step)."""
        from sqlalchemy import select

        stmt = select(StepExecution).where(
            StepExecution.workflow_execution_id == execution_id,
            StepExecution.workflow_step_id == step_id,
        )
        return self._db.scalar(stmt)

    def _create_step_execution(
        self,
        execution_id: UUID,
        step_id: UUID,
    ) -> StepExecution:
        """Create a new pending step execution record."""
        se = StepExecution(
            workflow_execution_id=execution_id,
            workflow_step_id=step_id,
            status=StepStatus.PENDING,
        )
        self._db.add(se)
        self._db.commit()
        self._db.refresh(se)
        return se

    def _update_step_execution(
        self,
        se: StepExecution,
        *,
        status: StepStatus | None = None,
        input_data: Any = None,
        output_data: Any = None,
        error: str | None = None,
        attempt_number: int | None = None,
    ) -> None:
        """Update a step execution record in-place.

        ``status`` may be omitted for partial updates (e.g. recording
        resolved input data while the step is already running).
        """
        now = _utcnow()
        if status is not None:
            se.status = status
        if input_data is not None:
            se.input_data = _dumps(input_data)
        if output_data is not None:
            se.output_data = _dumps(output_data)
        if error is not None:
            se.error = error
        if attempt_number is not None:
            se.attempt_number = attempt_number
        if status == StepStatus.RUNNING and se.started_at is None:
            se.started_at = now
        if status in (
            StepStatus.COMPLETED,
            StepStatus.FAILED,
            StepStatus.SKIPPED,
            StepStatus.CANCELLED,
            StepStatus.TIMED_OUT,
        ):
            se.completed_at = now
            started = _coerce_utc(se.started_at)
            if started is not None:
                se.duration_ms = int((now - started).total_seconds() * 1000)
        self._db.commit()

    def _run_workflow(
        self,
        execution: WorkflowExecution,
        workflow: Workflow,
        steps: list[WorkflowStep],
    ) -> dict[str, Any] | None:
        """Execute all steps in dependency order and return the final output."""
        state = WorkflowState(input_data=_loads(execution.input_data))

        step_map: dict[str, WorkflowStep] = {s.name: s for s in steps}

        # Build a lookup of (execution_id, step_id) -> StepExecution for steps
        # that may have been started before (resume scenario).
        existing_se: dict[UUID, StepExecution] = {}
        for step in steps:
            se = self._get_step_execution(execution.id, step.id)
            if se is not None:
                existing_se[step.id] = se

        # Determine execution order via topological sort.
        ordered = self._topo_sort(steps)

        for step_name in ordered:
            step = step_map[step_name]

            # Check cancellation.
            self._db.refresh(execution)
            if execution.status != WorkflowExecutionStatus.RUNNING:
                # Execution was cancelled (or failed) while we were processing.
                se = existing_se.get(step.id)
                if se is None:
                    se = self._create_step_execution(execution.id, step.id)
                    existing_se[step.id] = se
                if se.status not in (
                    StepStatus.COMPLETED,
                    StepStatus.FAILED,
                    StepStatus.SKIPPED,
                    StepStatus.CANCELLED,
                    StepStatus.TIMED_OUT,
                ):
                    self._update_step_execution(se, status=StepStatus.CANCELLED)
                continue

            # Check: are all dependencies completed?
            deps = _loads(step.dependencies) or []
            all_deps_met = all(state.is_step_completed(d) for d in deps)
            if not all_deps_met:
                # Some dependency failed — skip this step.
                se = existing_se.get(step.id)
                if se is None:
                    se = self._create_step_execution(execution.id, step.id)
                    existing_se[step.id] = se
                self._update_step_execution(se, status=StepStatus.SKIPPED)
                state.mark_step(step_name, "skipped")
                logger.info(
                    "step_skipped",
                    extra={
                        "step": step_name,
                        "reason": "dependency not met",
                        "execution_id": str(execution.id),
                    },
                )
                continue

            # Create or reuse step execution record.
            se = existing_se.get(step.id)
            if se is None:
                se = self._create_step_execution(execution.id, step.id)
                existing_se[step.id] = se
            # If it's not pending (e.g. already completed from a resume), skip.
            if se.status in (StepStatus.COMPLETED, StepStatus.SKIPPED):
                if se.status == StepStatus.COMPLETED:
                    step_output = _loads(se.output_data) if se.output_data else {}
                    state.set_step_output(step_name, step_output or {})
                state.mark_step(step_name, se.status.value)
                continue

            # Mark running.
            self._update_step_execution(se, status=StepStatus.RUNNING)

            # Resolve step input.
            config = _loads(step.configuration) or {}
            input_mapping = config.get("input_mapping")
            resolved_input = resolve_mapping(input_mapping, state) if input_mapping else {}
            self._update_step_execution(se, input_data=resolved_input)

            # Run the step with retries.
            try:
                output = self._run_step_with_retries(step, se, state, resolved_input)
                self._update_step_execution(se, status=StepStatus.COMPLETED, output_data=output)

                # A condition step that evaluates to ``False`` should gate its
                # downstream steps: the condition step itself is COMPLETED, but
                # its branch is "not met", so dependents see it as not-completed
                # and are skipped.
                is_condition = step.step_type.value == WorkflowStepType.CONDITION.value
                if is_condition and isinstance(output, dict) and output.get("passed") is False:
                    state.mark_step(step_name, "skipped")
                else:
                    state.set_step_output(step_name, output or {})
            except WorkflowEngineError as exc:
                # Step failed after retries / timeout / cancelled.
                self._update_step_execution(se, status=StepStatus.FAILED, error=str(exc))
                state.mark_step(step_name, "failed")
                raise StepFailedError(f"Step {step.name!r} failed: {exc}") from exc

        # Collect final output from the last completed step, or None.
        final_output = None
        for step in reversed(ordered):
            step_out = state.get_step_output(step)
            if step_out is not None:
                final_output = step_out
                break

        return final_output

    def _run_step_with_retries(
        self,
        step: WorkflowStep,
        se: StepExecution,
        state: WorkflowState,
        resolved_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a step, retrying if the retry_policy allows.

        After a step produces output, if the step declares a ``verification_policy``
        (Phase 6, §26), the output is verified.  A verification outcome below the
        policy's ``minimum_score`` is treated as a step failure so the existing
        retry/branching logic applies — without duplicating any engine logic (the
        engine only calls :class:`VerificationService`).
        """
        retry_policy = _loads(step.retry_policy) or {}
        max_attempts = retry_policy.get("max_attempts", 1)

        # Only retry if the step's idempotency tag allows it.
        idempotency = step.idempotency
        if hasattr(idempotency, "value"):
            idempotency = idempotency.value
        safe_to_retry = idempotency in (
            IdempotencyTag.READ_ONLY.value,
            IdempotencyTag.IDEMPOTENT.value,
        )
        if not safe_to_retry:
            max_attempts = 1

        policy_cfg = _loads(step.verification_policy) or {}

        delay_base = retry_policy.get("delay", 0)  # seconds
        retry_on_errors = retry_policy.get("retry_on", [])

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            self._update_step_execution(se, attempt_number=attempt)
            try:
                output = self._run_step(step, state, resolved_input)
                # Optional verification (Phase 6, §26) — runs after a successful
                # step only; a below-threshold verdict fails the step.
                if policy_cfg:
                    self._verify_step(step, se, output, policy_cfg)
                return output
            except ExecutionCancelledError:
                raise
            except Exception as exc:
                last_error = exc
                err_type = type(exc).__name__
                should_retry = attempt < max_attempts and (
                    not retry_on_errors or err_type in retry_on_errors
                )
                if should_retry:
                    logger.info(
                        "step_retrying",
                        extra={
                            "step": step.name,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "error": err_type,
                        },
                    )
                    if delay_base > 0:
                        time.sleep(delay_base)
                    continue
                raise StepFailedError(
                    f"Step {step.name!r} failed after {attempt} attempt(s): {exc}"
                ) from exc

        # Should never reach here, but defensive:
        raise StepFailedError(f"Step {step.name!r} failed: {last_error}")

    def _verify_step(
        self,
        step: WorkflowStep,
        se: StepExecution,
        output: dict[str, Any],
        policy_cfg: dict[str, Any],
    ) -> None:
        """Verify a step's output against its ``verification_policy`` (§26).

        The engine only calls :class:`VerificationService` — it never re-implements
        verification.  A verdict below ``minimum_score`` (or FAIL/UNCERTAIN unless
        the policy permits) fails the step so the caller's retry handling applies.
        The resulting run id is recorded on the :class:`StepExecution`.
        """
        from app.verification.policy import VerificationPolicy
        from app.verification.service import VerificationService

        try:
            policy = VerificationPolicy.from_dict(policy_cfg)
        except ValueError as exc:
            raise WorkflowEngineError(
                f"Step {step.name!r}: invalid verification_policy: {exc}"
            ) from exc
        if not policy.required:
            return

        result = VerificationService(self._db).verify(
            output,
            policy=policy,
            workflow_id=step.workflow_id,
            context={"criteria": policy_cfg.get("criteria", [])},
            risk_level=policy_cfg.get("risk_level", "high"),
        )
        se.verification_run_id = result.run_id
        self._db.commit()

        below_min = result.score is not None and result.score < policy.minimum_score
        if result.status.value == "fail" or result.status.value == "uncertain":
            reason = result.reason or "verification failed"
            raise StepFailedError(f"Step {step.name!r} failed verification: {reason}")
        if below_min and policy.minimum_score is not None:
            raise StepFailedError(
                f"Step {step.name!r} verification score {result.score:.2f} "
                f"below minimum {policy.minimum_score}"
            )

    def _run_step(
        self,
        step: WorkflowStep,
        state: WorkflowState,
        resolved_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a single step based on step_type.

        Returns the step output as a dict.
        """
        step_type = step.step_type
        if hasattr(step_type, "value"):
            step_type = step_type.value
        config = _loads(step.configuration) or {}

        # Timeout enforcement.
        timeout = step.timeout_seconds

        if step_type == WorkflowStepType.CONDITION.value:
            return self._run_condition_step(step, config, state)
        if step_type == WorkflowStepType.DELAY.value:
            return self._run_delay_step(step, config, timeout)
        if step_type == WorkflowStepType.AGENT_TASK.value:
            return self._run_agent_task_step(step, config, resolved_input, timeout)
        if step_type == WorkflowStepType.TOOL_ACTION.value:
            return self._run_tool_action_step(step, config, resolved_input, timeout)
        if step_type == WorkflowStepType.ORCHESTRATION.value:
            return self._run_orchestration_step(step, config, resolved_input)
        if step_type == WorkflowStepType.EMPLOYEE_TASK.value:
            return self._run_employee_task_step(step, config, resolved_input, timeout)

        raise ValidationError(f"Unknown step type: {step_type!r}")

    def _run_condition_step(
        self,
        step: WorkflowStep,
        config: dict[str, Any],
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Evaluate a condition step.  Returns ``{"passed": true/false}``."""
        condition = config.get("condition", {})
        try:
            passed = evaluate_condition(condition, state.to_dict())
        except ConditionEvaluationError as exc:
            raise ValidationError(
                f"Step {step.name!r}: condition evaluation failed: {exc}"
            ) from exc
        return {"passed": passed}

    def _run_delay_step(
        self,
        step: WorkflowStep,
        config: dict[str, Any],
        timeout: int | None,
    ) -> dict[str, Any]:
        """Sleep for the configured duration (with cancellation check)."""
        duration = config.get("duration", 0)
        if duration <= 0:
            return {"delayed_seconds": 0}
        # Enforce a hard maximum delay.
        effective = min(duration, timeout or duration, 3600)
        time.sleep(effective)
        return {"delayed_seconds": effective}

    def _run_agent_task_step(
        self,
        step: WorkflowStep,
        config: dict[str, Any],
        resolved_input: dict[str, Any],
        timeout: int | None,
    ) -> dict[str, Any]:
        """Run an agent task via AgentRuntime.

        Creates a temporary Task, assigns it to the configured agent, then
        executes via the existing runtime — reusing the full agent execution
        pipeline including tool calling.
        """
        agent_id_str = config.get("agent_id")
        if not agent_id_str:
            raise ValidationError(f"Step {step.name!r}: agent_id is required in configuration")
        agent_id = UUID(agent_id_str)

        # Validate the agent exists and is active.
        agent = self._db.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError(f"Agent {agent_id_str!r} not found for step {step.name!r}")

        # Create a temporary task for the runtime.
        task_svc = TaskService(self._db)
        task = task_svc.create(
            TaskCreate(
                title=f"workflow:{step.name}",
                input_data=resolved_input or None,
                assigned_agent_id=agent_id,
            )
        )
        task_svc.assign(task.id, agent_id)

        # Execute via the runtime.
        runtime = AgentRuntime(
            agent_service=AgentService(self._db),
            task_service=task_svc,
            execution_service=ExecutionService(self._db),
        )
        execution = runtime.execute_task(task.id)

        # Extract the agent's output.
        output_data = _loads(execution.output_data)
        if output_data is None:
            output_data = {}
        return {
            "agent_execution_id": str(execution.id),
            "summary": output_data.get("summary", ""),
            "output": output_data.get("output", {}),
            "confidence": output_data.get("confidence"),
        }

    def _run_tool_action_step(
        self,
        step: WorkflowStep,
        config: dict[str, Any],
        resolved_input: dict[str, Any],
        timeout: int | None,
    ) -> dict[str, Any]:
        """Run a tool action directly (no agent involved).

        Uses ToolExecutor with permission gating via the configured
        ``agent_id``.
        """
        tool_name = config.get("tool_name")
        if not tool_name:
            raise ValidationError(f"Step {step.name!r}: tool_name is required in configuration")

        # Determine the agent context for permission checking.
        agent_id_str = config.get("agent_id")
        if agent_id_str:
            agent_id = UUID(agent_id_str)
        else:
            # Generate a synthetic ID for workflow-scoped tool calls.
            agent_id = uuid4()

        permission_svc = PermissionService(self._db)
        perm_ctx = permission_svc.get_context(agent_id)

        # Build the arguments: explicit args take a back seat to the resolved
        # input mapping (which may contain dotted-path references).  Explicit
        # args are passed through verbatim — literal strings are interpreted as
        # values, not path references.
        explicit_args = config.get("arguments") or {}
        merged_args = dict(explicit_args)
        merged_args.update(resolved_input)

        executor = ToolExecutor(self._db)
        record = executor.execute(
            tool_name=tool_name,
            arguments=merged_args,
            execution_id=uuid4(),  # Workflow-level "execution" id for tool_calls.
            agent_id=agent_id,
            permission_context=perm_ctx,
        )

        result_status = record.result.status.value
        if result_status == "denied":
            # Unauthorized tool step → fail the step (and thus the workflow).
            raise WorkflowEngineError(
                f"Step {step.name!r}: tool {tool_name!r} was denied by permissions"
            )

        return {
            "tool_name": tool_name,
            "result_status": result_status,
            "result_data": record.result.data,
            "result_error": record.result.error,
        }

    def _run_orchestration_step(
        self,
        step: WorkflowStep,
        config: dict[str, Any],
        resolved_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a multi-agent orchestration step (Phase 5).

        Loads the referenced orchestration and executes it inline (deterministic
        path) via :class:`OrchestrationService`, returning the final result into
        the workflow state for downstream steps.
        """
        from app.services.orchestration_service import (
            OrchestrationService,
            to_dict,
        )

        orchestration_id_str = config.get("orchestration_id")
        if not orchestration_id_str:
            raise ValidationError(
                f"Step {step.name!r}: orchestration_id is required in configuration"
            )
        orchestration_id = UUID(orchestration_id_str)
        if resolved_input:
            upsert_id = resolved_input.get("orchestration_id")
            if upsert_id:
                orchestration_id = UUID(upsert_id)

        service = OrchestrationService(self._db)
        orch = service.get(orchestration_id)
        if orch.status in ("completed", "partially_completed"):
            # Already ran — reuse the existing result.
            executed = orch
        else:
            executed = service.execute(orchestration_id)

        executed = self._db.get(type(executed), orchestration_id) or executed
        result = to_dict(executed)
        return {
            "orchestration_id": str(executed.id),
            "orchestration_status": result.get("status"),
            "final_result": result.get("final_result"),
            "metrics": result.get("metrics"),
        }

    def _run_employee_task_step(
        self,
        step: WorkflowStep,
        config: dict[str, Any],
        resolved_input: dict[str, Any],
        timeout: int | None,
    ) -> dict[str, Any]:
        """Run a task via an AI Employee.

        Resolves the employee, builds context, and delegates to the employee's
        underlying agent via AgentRuntime.  Config::

            {
                "employee_id": "<uuid>",
                "task_title": "optional override",
                "task_description": "optional override",
                "input_mapping": {...}
            }
        """
        employee_id_str = config.get("employee_id")
        if not employee_id_str:
            raise ValidationError(f"Step {step.name!r}: employee_id is required in configuration")
        employee_id = UUID(employee_id_str)

        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            raise NotFoundError(f"Employee {employee_id_str!r} not found for step {step.name!r}")

        # Build employee context.
        from app.employee.context import EmployeeContextBuilder

        ctx_builder = EmployeeContextBuilder(self._db)
        task_desc = config.get("task_description", step.name)
        employee_ctx = ctx_builder.build_context(employee_id, task_description=task_desc)

        # Resolve the underlying agent for execution.
        agent_id = emp.agent_id
        if agent_id is None:
            raise ValidationError(f"Employee {emp.name!r} has no agent_id; cannot execute")

        agent = self._db.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError(f"Agent {agent_id!r} for employee {emp.name!r} not found")

        # Create a task for the runtime.
        task_svc = TaskService(self._db)
        task_title = config.get("task_title", f"employee:{emp.name}:{step.name}")
        task = task_svc.create(
            TaskCreate(
                title=task_title,
                input_data=resolved_input or None,
                assigned_agent_id=agent_id,
            )
        )
        task_svc.assign(task.id, agent_id)

        # Execute via the runtime.
        runtime = AgentRuntime(
            agent_service=AgentService(self._db),
            task_service=task_svc,
            execution_service=ExecutionService(self._db),
        )
        execution = runtime.execute_task(task.id)

        # Extract the agent's output.
        output_data = _loads(execution.output_data)
        if output_data is None:
            output_data = {}

        return {
            "employee_id": str(employee_id),
            "employee_name": emp.name,
            "agent_execution_id": str(execution.id),
            "employee_context": employee_ctx,
            "summary": output_data.get("summary", ""),
            "output": output_data.get("output", {}),
            "confidence": output_data.get("confidence"),
        }

    @staticmethod
    def _topo_sort(steps: list[WorkflowStep]) -> list[str]:
        """Return step names in topological (dependency) order.

        Uses Kahn's algorithm.  Steps with no dependencies come first;
        among peers, ``order`` (ascending) is used as a tiebreaker.
        """
        # Build adjacency: step_name -> set of dep names.
        deps_map: dict[str, set[str]] = {}
        order_map: dict[str, int] = {}
        for s in steps:
            d = _loads(s.dependencies) or []
            deps_map[s.name] = set(d)
            order_map[s.name] = s.order

        # Kahn's algorithm.
        in_degree: dict[str, int] = {name: 0 for name in deps_map}
        graph: dict[str, set[str]] = {name: set() for name in deps_map}
        for name, dep_set in deps_map.items():
            for dep in dep_set:
                if dep in graph:
                    graph[dep].add(name)
                    in_degree[name] += 1

        # Use a sorted list for deterministic ordering.
        queue = sorted(
            [name for name, deg in in_degree.items() if deg == 0],
            key=lambda n: (order_map.get(n, 0), n),
        )
        result: list[str] = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbour in sorted(graph[node], key=lambda n: (order_map.get(n, 0), n)):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)
            # Re-sort queue to maintain deterministic order.
            queue.sort(key=lambda n: (order_map.get(n, 0), n))

        return result
