"""Multi-agent orchestration endpoints (Phase 5)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.models.orchestration import OrchestrationStatus
from app.db.session import get_db
from app.schemas.orchestration import (
    AssignmentRead,
    ContextEntryRead,
    MessageRead,
    OrchestrationCreate,
    OrchestrationList,
    OrchestrationRead,
    OrchestrationResultRead,
    OrchestrationTaskRead,
    ReviewComplete,
    ReviewCreate,
    ReviewRead,
    TimelineEvent,
)
from app.services.orchestration_service import (
    OrchestrationService,
    assignment_to_dict,
    context_to_dict,
    message_to_dict,
    result_to_dict,
    review_to_dict,
    task_to_dict,
    timeline_to_dict,
    to_dict,
)

router = APIRouter(tags=["orchestrations"], prefix="/orchestrations")


@router.post(
    "",
    response_model=OrchestrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an orchestration",
)
def create_orchestration(
    payload: OrchestrationCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> OrchestrationRead:
    orch = OrchestrationService(db).create(payload)
    return OrchestrationRead.model_validate(to_dict(orch))


@router.get(
    "",
    response_model=OrchestrationList,
    summary="List orchestrations",
)
def list_orchestrations(
    orchid_status: OrchestrationStatus | None = Query(default=None, alias="status"),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> OrchestrationList:
    orch = OrchestrationService(db).list(status=orchid_status)
    return OrchestrationList(
        items=[OrchestrationRead.model_validate(to_dict(o)) for o in orch],
        total=len(orch),
    )


@router.get(
    "/{orchestration_id}",
    response_model=OrchestrationRead,
    summary="Get an orchestration",
)
def get_orchestration(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> OrchestrationRead:
    orch = OrchestrationService(db).get(orchestration_id)
    return OrchestrationRead.model_validate(to_dict(orch))


@router.delete(
    "/{orchestration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an orchestration (non-running)",
)
def delete_orchestration(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    OrchestrationService(db).delete(orchestration_id)


@router.post(
    "/{orchestration_id}/execute",
    response_model=OrchestrationRead,
    summary="Run an orchestration to completion",
)
def execute_orchestration(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> OrchestrationRead:
    orch = OrchestrationService(db).execute(orchestration_id)
    return OrchestrationRead.model_validate(to_dict(orch))


@router.post(
    "/{orchestration_id}/cancel",
    response_model=OrchestrationRead,
    summary="Cancel an orchestration",
)
def cancel_orchestration(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> OrchestrationRead:
    orch = OrchestrationService(db).cancel(orchestration_id)
    return OrchestrationRead.model_validate(to_dict(orch))


# ── Read APIs ──────────────────────────────────────────────────────────────


@router.get(
    "/{orchestration_id}/tasks",
    response_model=list[OrchestrationTaskRead],
    summary="List an orchestration's tasks",
)
def get_tasks(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[OrchestrationTaskRead]:
    return [
        OrchestrationTaskRead.model_validate(task_to_dict(t))
        for t in OrchestrationService(db).get_tasks(orchestration_id)
    ]


@router.get(
    "/{orchestration_id}/assignments",
    response_model=list[AssignmentRead],
    summary="List an orchestration's agent assignments",
)
def get_assignments(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[AssignmentRead]:
    return [
        AssignmentRead.model_validate(assignment_to_dict(a))
        for a in OrchestrationService(db).get_assignments(orchestration_id)
    ]


@router.get(
    "/{orchestration_id}/messages",
    response_model=list[MessageRead],
    summary="List an orchestration's inter-agent messages",
)
def get_messages(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[MessageRead]:
    return [
        MessageRead.model_validate(message_to_dict(m))
        for m in OrchestrationService(db).get_messages(orchestration_id)
    ]


@router.get(
    "/{orchestration_id}/results",
    response_model=list[OrchestrationResultRead],
    summary="List an orchestration's aggregated results",
)
def get_results(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[OrchestrationResultRead]:
    return [
        OrchestrationResultRead.model_validate(result_to_dict(r))
        for r in OrchestrationService(db).get_results(orchestration_id)
    ]


@router.get(
    "/{orchestration_id}/context",
    response_model=list[ContextEntryRead],
    summary="List an orchestration's shared context",
)
def get_context(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ContextEntryRead]:
    return [
        ContextEntryRead.model_validate(context_to_dict(c))
        for c in OrchestrationService(db).get_context(orchestration_id)
    ]


@router.get(
    "/{orchestration_id}/timeline",
    response_model=list[TimelineEvent],
    summary="Get an orchestration's observable timeline",
)
def get_timeline(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[TimelineEvent]:
    service = OrchestrationService(db)
    orch = service.get(orchestration_id)
    tasks = service.get_tasks(orchestration_id)
    return [TimelineEvent(**e) for e in timeline_to_dict(orch, tasks)]


# ── Reviews ────────────────────────────────────────────────────────────────


@router.post(
    "/{orchestration_id}/reviews",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request a review of an agent's output",
)
def create_review(
    orchestration_id: UUID,
    payload: ReviewCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ReviewRead:
    review = OrchestrationService(db).create_review(orchestration_id, payload)
    return ReviewRead.model_validate(review_to_dict(review))


@router.post(
    "/{orchestration_id}/reviews/{review_id}/complete",
    response_model=ReviewRead,
    summary="Record a verdict for an open review",
)
def complete_review(
    orchestration_id: UUID,
    review_id: UUID,
    payload: ReviewComplete,
    db: Session = Depends(get_db),  # noqa: B008
) -> ReviewRead:
    review = OrchestrationService(db).complete_review(orchestration_id, review_id, payload)
    return ReviewRead.model_validate(review_to_dict(review))


@router.get(
    "/{orchestration_id}/reviews",
    response_model=list[ReviewRead],
    summary="List an orchestration's reviews",
)
def get_reviews(
    orchestration_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ReviewRead]:
    return [
        ReviewRead.model_validate(review_to_dict(r))
        for r in OrchestrationService(db).get_reviews(orchestration_id)
    ]
