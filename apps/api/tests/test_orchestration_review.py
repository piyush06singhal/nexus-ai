"""Tests for the agent review foundation (spec §16, §33)."""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import NotFoundError
from app.db.models.orchestration import ReviewVerdict
from app.orchestration.review import AgentReviewService, ReviewError, ReviewPolicy
from app.services.orchestration_service import OrchestrationService


@pytest.fixture
def orchestration(db):
    return OrchestrationService(db).create(
        __import__(
            "app.schemas.orchestration", fromlist=["OrchestrationCreate"]
        ).OrchestrationCreate(objective="test objective")
    )


def test_request_creates_pending_review(db, orchestration):
    reviewer = uuid.uuid4()
    service = AgentReviewService(db)
    review = service.request(orchestration.id, reviewer, content="please review")
    assert review.verdict == ReviewVerdict.PENDING
    assert review.reviewer_agent_id == reviewer
    assert review.iteration == 1


def test_approval_sets_verdict(db, orchestration):
    service = AgentReviewService(db)
    review = service.request(orchestration.id, uuid.uuid4())
    completed = service.complete(review.id, ReviewVerdict.APPROVED, "looks good")
    assert completed.verdict == ReviewVerdict.APPROVED
    assert completed.response_content == "looks good"
    assert completed.completed_at is not None


def test_rejection_followed_by_revision(db, orchestration):
    service = AgentReviewService(db)
    review = service.request(orchestration.id, uuid.uuid4(), content="check")
    service.complete(review.id, ReviewVerdict.REJECTED, "needs work")
    revised = service.request_revision(review.id, "fix the numbers")
    assert revised.verdict == ReviewVerdict.REQUEST_REVISION
    assert revised.iteration == 2


def test_max_iterations_forces_approval(db, orchestration):
    service = AgentReviewService(db, policy=ReviewPolicy(max_iterations=1))
    review = service.request(orchestration.id, uuid.uuid4())
    # First rejection at max iterations closes as approved.
    closed = service.complete(review.id, ReviewVerdict.REJECTED)
    assert closed.verdict == ReviewVerdict.APPROVED


def test_invalid_verdict_rejected(db, orchestration):
    service = AgentReviewService(db)
    review = service.request(orchestration.id, uuid.uuid4())
    with pytest.raises(ReviewError):
        service.complete(review.id, "bogus")


def test_list_returns_all_reviews(db, orchestration):
    service = AgentReviewService(db)
    service.request(orchestration.id, uuid.uuid4())
    service.request(orchestration.id, uuid.uuid4())
    service.request(orchestration.id, uuid.uuid4())
    assert len(service.list(orchestration.id)) == 3


def test_get_missing_review_raises(db, orchestration):
    service = AgentReviewService(db)
    with pytest.raises(NotFoundError):
        service.get(uuid.uuid4())


def test_string_verdict_accepted(db, orchestration):
    service = AgentReviewService(db)
    review = service.request(orchestration.id, uuid.uuid4())
    closed = service.complete(review.id, "approved")
    assert closed.verdict == ReviewVerdict.APPROVED
