"""Multi-agent orchestration service.

Thin CRUD, lifecycle, and serialization over the orchestration ORM models —
the API and engine layers stay decoupled from the DB. Mirrors
:class:`app.services.workflow_service.WorkflowService`.

Execution runs inline (determinstic) via :class:`app.orchestration.orchestrator.Orchestrator`
on a fresh engine ``sync_session_factory`` session so parallel task workers get
their own SQLAlchemy sessions (SQLite StaticPool-safe).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.db.models.orchestration import (
    AgentAssignment,
    AgentMessage,
    AgentReview,
    Orchestration,
    OrchestrationContext,
    OrchestrationResult,
    OrchestrationStatus,
    OrchestrationTask,
)
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.policies import OrchestrationLimits
from app.schemas.orchestration import (
    OrchestrationCreate,
    ReviewComplete,
    ReviewCreate,
)


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _dumps(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


# ── Serialization helpers ─────────────────────────────────────────────────────


def to_dict(orch: Orchestration) -> dict:
    return {
        "id": str(orch.id),
        "objective": orch.objective,
        "status": orch.status.value,
        "strategy": orch.strategy,
        "selected_agents": _loads(orch.selected_agents),
        "execution_graph": _loads(orch.execution_graph),
        "final_result": _loads(orch.final_result),
        "error": orch.error,
        "metrics": _loads(orch.metrics),
        "verification_policy": _loads(orch.verification_policy),
        "started_at": orch.started_at,
        "completed_at": orch.completed_at,
        "duration_ms": orch.duration_ms,
        "created_at": orch.created_at,
        "updated_at": orch.updated_at,
    }


def task_to_dict(task: OrchestrationTask) -> dict:
    return {
        "id": str(task.id),
        "orchestration_id": str(task.orchestration_id),
        "name": task.name,
        "description": task.description,
        "required_capabilities": _loads(task.required_capabilities),
        "dependencies": _loads(task.dependencies),
        "status": task.status.value,
        "agent_id": task.agent_id,
        "input_context": _loads(task.input_context),
        "output_data": _loads(task.output_data),
        "result_summary": task.result_summary,
        "attempt_number": task.attempt_number,
        "error": task.error,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "duration_ms": task.duration_ms,
        "created_at": task.created_at,
    }


def assignment_to_dict(assignment: AgentAssignment) -> dict:
    return {
        "id": str(assignment.id),
        "orchestration_id": str(assignment.orchestration_id),
        "task_id": str(assignment.task_id),
        "agent_id": assignment.agent_id,
        "role": assignment.role,
        "instructions": assignment.instructions,
        "priority": assignment.priority,
        "dependencies": _loads(assignment.dependencies),
        "status": assignment.status.value,
        "input_context": _loads(assignment.input_context),
        "output_data": _loads(assignment.output_data),
        "error": assignment.error,
        "attempt_number": assignment.attempt_number,
        "agent_execution_id": assignment.agent_execution_id,
        "started_at": assignment.started_at,
        "completed_at": assignment.completed_at,
    }


def message_to_dict(message: AgentMessage) -> dict:
    return {
        "id": str(message.id),
        "orchestration_id": str(message.orchestration_id),
        "sender_agent_id": message.sender_agent_id,
        "recipient_agent_id": message.recipient_agent_id,
        "message_type": message.message_type.value,
        "content": message.content,
        "metadata": _loads(message.metadata_json),
        "correlation_id": message.correlation_id,
        "task_id": message.task_id,
        "created_at": message.created_at,
    }


def result_to_dict(result: OrchestrationResult) -> dict:
    return {
        "id": str(result.id),
        "orchestration_id": str(result.orchestration_id),
        "task_id": result.task_id,
        "assignment_id": result.assignment_id,
        "agent_id": result.agent_id,
        "content": result.content,
        "structured_data": _loads(result.structured_data),
        "confidence": result.confidence,
        "metadata": _loads(result.metadata_json),
        "created_at": result.created_at,
    }


def context_to_dict(entry: OrchestrationContext) -> dict:
    return {
        "id": str(entry.id),
        "orchestration_id": str(entry.orchestration_id),
        "key": entry.key,
        "value": _loads(entry.value),
        "kind": entry.kind,
        "agent_id": entry.agent_id,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def review_to_dict(review: AgentReview) -> dict:
    return {
        "id": str(review.id),
        "orchestration_id": str(review.orchestration_id),
        "task_id": review.task_id,
        "reviewer_agent_id": review.reviewer_agent_id,
        "reviewee_agent_id": review.reviewee_agent_id,
        "request_content": review.request_content,
        "response_content": review.response_content,
        "verdict": review.verdict.value,
        "iteration": review.iteration,
        "created_at": review.created_at,
        "completed_at": review.completed_at,
    }


def timeline_to_dict(
    orch: Orchestration, tasks: list[OrchestrationTask] | None = None
) -> list[dict]:
    """Assemble a chronological, observable timeline of the run.

    ``tasks`` may be passed in to include per-task events; the orchestration
    object alone yields the lifecycle-level events.
    """
    events: list[dict] = []
    events.append(
        {
            "timestamp": orch.created_at,
            "event_type": "created",
            "status": orch.status.value,
            "description": f"Orchestration created for objective: {orch.objective[:80]}",
            "entity_id": str(orch.id),
        }
    )
    if orch.started_at is not None:
        events.append(
            {
                "timestamp": orch.started_at,
                "event_type": "started",
                "status": "running",
                "description": "Orchestration execution started",
                "entity_id": str(orch.id),
            }
        )
    for task in tasks or []:
        events.append(
            {
                "timestamp": task.created_at,
                "event_type": "task_planned",
                "status": task.status.value,
                "description": f"Task planned: {task.name}",
                "entity_id": str(task.id),
            }
        )
        if task.completed_at is not None:
            events.append(
                {
                    "timestamp": task.completed_at,
                    "event_type": "task_finished",
                    "status": task.status.value,
                    "description": f"Task finished: {task.name}",
                    "entity_id": str(task.id),
                }
            )
    if orch.completed_at is not None:
        events.append(
            {
                "timestamp": orch.completed_at,
                "event_type": "completed",
                "status": orch.status.value,
                "description": f"Orchestration finished with status {orch.status.value}",
                "entity_id": str(orch.id),
            }
        )
    events.sort(key=lambda e: e["timestamp"] or datetime.min)
    return events


# ── Service ───────────────────────────────────────────────────────────────────


class OrchestrationService:
    """Create, read, execute, and cancel multi-agent orchestrations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── CRUD ───────────────────────────────────────────────────────────────

    def create(self, payload: OrchestrationCreate) -> Orchestration:
        orch = Orchestration(
            objective=payload.objective,
            strategy=payload.strategy or settings.orchestration_default_strategy,
            status=OrchestrationStatus.CREATED,
            verification_policy=_dumps(payload.verification_policy),
        )
        self._db.add(orch)
        self._db.commit()
        self._db.refresh(orch)
        return orch

    def get(self, orchestration_id: UUID) -> Orchestration:
        orch = self._db.get(Orchestration, orchestration_id)
        if orch is None:
            raise NotFoundError(f"Orchestration {orchestration_id} not found")
        return orch

    def list(self, *, status: OrchestrationStatus | None = None) -> list[Orchestration]:
        stmt = select(Orchestration).order_by(Orchestration.created_at.desc())
        if status is not None:
            stmt = stmt.where(Orchestration.status == status)
        return list(self._db.scalars(stmt).all())

    def delete(self, orchestration_id: UUID) -> None:
        orch = self.get(orchestration_id)
        if orch.status in (
            OrchestrationStatus.RUNNING,
            OrchestrationStatus.PLANNING,
            OrchestrationStatus.ASSIGNING,
            OrchestrationStatus.SYNTHESIZING,
        ):
            raise ValidationError(f"Cannot delete an orchestration in {orch.status.value!r} status")
        self._db.delete(orch)
        self._db.commit()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def execute(self, orchestration_id: UUID) -> Orchestration:
        orch = self.get(orchestration_id)
        if orch.status != OrchestrationStatus.CREATED:
            raise ValidationError(
                f"Cannot execute orchestration in {orch.status.value!r} status (must be created)"
            )
        limits = OrchestrationLimits.from_settings(settings)
        # Workers get their own SQLAlchemy sessions bound to the SAME engine the
        # control session uses (SQLite StaticPool safe, Postgres pool_pre_ping).
        from sqlalchemy.orm import sessionmaker

        session_factory = sessionmaker(bind=self._db.get_bind(), expire_on_commit=False)
        orchestrator = Orchestrator(
            session_factory,
            limits=limits,
        )
        return orchestrator.execute(orch, self._db)

    def cancel(self, orchestration_id: UUID) -> Orchestration:
        orch = self.get(orchestration_id)
        if orch.status not in (
            OrchestrationStatus.CREATED,
            OrchestrationStatus.RUNNING,
        ):
            raise ValidationError(f"Cannot cancel orchestration in {orch.status.value!r} status")
        if orch.status == OrchestrationStatus.CREATED:
            orch.status = OrchestrationStatus.CANCELLED
            orch.completed_at = datetime.now(UTC)
        else:
            # Terminate gracefully: the engine observes the flag and stops
            # launching new tasks; already-completed tasks stay completed.
            orch.status = OrchestrationStatus.CANCELLED
            orch.error = "Cancelled by user"
            orch.completed_at = datetime.now(UTC)
        self._db.commit()
        self._db.refresh(orch)
        return orch

    # ── Read APIs ──────────────────────────────────────────────────────────

    def get_tasks(self, orchestration_id: UUID) -> list[OrchestrationTask]:
        self.get(orchestration_id)
        stmt = (
            select(OrchestrationTask)
            .where(OrchestrationTask.orchestration_id == orchestration_id)
            .order_by(OrchestrationTask.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def get_assignments(self, orchestration_id: UUID) -> list[AgentAssignment]:
        self.get(orchestration_id)
        stmt = (
            select(AgentAssignment)
            .where(AgentAssignment.orchestration_id == orchestration_id)
            .order_by(AgentAssignment.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def get_messages(self, orchestration_id: UUID) -> list[AgentMessage]:
        self.get(orchestration_id)
        stmt = (
            select(AgentMessage)
            .where(AgentMessage.orchestration_id == orchestration_id)
            .order_by(AgentMessage.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def get_results(self, orchestration_id: UUID) -> list[OrchestrationResult]:
        self.get(orchestration_id)
        stmt = (
            select(OrchestrationResult)
            .where(OrchestrationResult.orchestration_id == orchestration_id)
            .order_by(OrchestrationResult.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def get_context(self, orchestration_id: UUID) -> list[OrchestrationContext]:
        self.get(orchestration_id)
        stmt = (
            select(OrchestrationContext)
            .where(OrchestrationContext.orchestration_id == orchestration_id)
            .order_by(OrchestrationContext.created_at)
        )
        return list(self._db.scalars(stmt).all())

    def get_reviews(self, orchestration_id: UUID) -> list[AgentReview]:
        self.get(orchestration_id)
        stmt = (
            select(AgentReview)
            .where(AgentReview.orchestration_id == orchestration_id)
            .order_by(AgentReview.created_at)
        )
        return list(self._db.scalars(stmt).all())

    # ── Reviews ────────────────────────────────────────────────────────────

    def create_review(self, orchestration_id: UUID, payload: ReviewCreate) -> AgentReview:
        self.get(orchestration_id)
        from app.orchestration.review import AgentReviewService, ReviewPolicy

        service = AgentReviewService(
            self._db,
            policy=ReviewPolicy(),
        )
        return service.request(
            orchestration_id,
            reviewer_agent_id=UUID(str(payload.reviewer_agent_id)),
            task_id=payload.task_id,
            reviewee_agent_id=payload.reviewee_agent_id,
            content=payload.content,
        )

    def complete_review(
        self, orchestration_id: UUID, review_id: UUID, payload: ReviewComplete
    ) -> AgentReview:
        self.get(orchestration_id)
        from app.orchestration.review import AgentReviewService

        service = AgentReviewService(self._db)
        return service.complete(review_id, payload.verdict, payload.response_content)
